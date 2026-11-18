import json
from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.accounts import scope
from apps.accounts.i18n import tr
from apps.accounts.models import User
from apps.alerts import mother as mother_msg
from apps.alerts import services
from apps.alerts.models import Referral
from apps.dashboard.stats import COLOR_RANK
from apps.risk.engine import evaluate, mother_context
from apps.voice import mock

from .forms import PatientForm, VisitForm
from .models import AccessLog, Patient
from .schedule import anc_plan, next_anc_date, registration_week


def _patient_or_404(user, pk):
    qs = scope.patients_for(user, Patient.objects.select_related("mavze__clinic__district"))
    return get_object_or_404(qs, pk=pk)


@login_required
def patient_list(request):
    qs = scope.patients_for(request.user, Patient.objects.select_related("mavze__clinic__district"))
    status = request.GET.get("status", "pregnant")
    if status != "all":
        qs = qs.filter(status=status)
    if color := request.GET.get("color"):
        qs = qs.filter(current_color=color)
    if request.GET.get("missed"):
        qs = qs.filter(next_visit_date__lt=date.today(), status=Patient.PREGNANT)
    if q := request.GET.get("q", "").strip():
        for t in q.split():
            qs = qs.filter(Q(last_name__icontains=t) | Q(first_name__icontains=t) | Q(middle_name__icontains=t)
                           | Q(phone__icontains=t))
    if clinic := request.GET.get("clinic"):
        qs = qs.filter(mavze__clinic_id=clinic)
    if mavze := request.GET.get("mavze"):
        qs = qs.filter(mavze_id=mavze)
    qs = qs.annotate(rank=COLOR_RANK).order_by("-rank", "last_name")
    page = Paginator(qs, 30).get_page(request.GET.get("page"))
    params = request.GET.copy()
    params.pop("page", None)
    return render(request, "patients/list.html", {"page": page, "params": params.urlencode(),
                                                  "total": page.paginator.count})


@login_required
def patient_detail(request, pk):
    p = _patient_or_404(request.user, pk)
    visits = mother_msg.attach(p.visits.select_related("doctor").order_by("-visit_date", "-created_at"), "visit")
    chart_visits = list(reversed(visits))
    chart = {
        "labels": [v.visit_date.strftime("%d.%m") for v in chart_visits],
        "hb": [v.hb for v in chart_visits],
        "sys": [v.bp_sys for v in chart_visits],
        "dia": [v.bp_dia for v in chart_visits],
    }
    AccessLog.log(request, p, AccessLog.VIEW)
    can_audit = request.user.role in (User.OVABMU, User.DISTRICT) or scope.can_edit_clinical(request.user, p.clinic)
    return render(request, "patients/detail.html", {
        "audit": p.access_logs.select_related("user")[:30] if can_audit else None,
        "p": p, "visits": visits, "chart": chart, "anc": anc_plan(p, visits),
        "reg_week": registration_week(p, visits),
        "children": p.children.all(),
        "alerts": mother_msg.attach(p.alerts.filter(child__isnull=True)[:10], "alert"),
        "referrals": p.referrals.filter(child__isnull=True),
        "can_edit": scope.can_edit_clinical(request.user, p.clinic),
        "can_child": scope.can_edit_child(request.user, p.clinic) or scope.can_edit_clinical(request.user, p.clinic),
        "can_refer": scope.can_refer(request.user),
        "referral_levels": Referral.LEVEL_CHOICES,
    })


@login_required
def patient_create(request):
    scope.require(scope.can_edit_clinical(request.user, request.user.clinic))
    form = PatientForm(request.POST or None, clinic=request.user.clinic, lang=request.lang)
    if request.method == "POST" and form.is_valid():
        p = form.save(commit=False)
        p.next_visit_date = date.today()
        if p.consent and not p.consent_at:
            p.consent_at = date.today()
        p.save()
        AccessLog.log(request, p, AccessLog.CREATE)
        messages.success(request, f"{p.short_name} ro'yxatga olindi. Endi birinchi ko'rikni kiriting.")
        return redirect("visit_create", pk=p.pk)
    return render(request, "patients/form.html", {"form": form, "title": tr(request, "Yangi homilador ayolni ro'yxatga olish")})


@login_required
def patient_edit(request, pk):
    p = _patient_or_404(request.user, pk)
    scope.require(scope.can_edit_clinical(request.user, p.clinic))
    form = PatientForm(request.POST or None, instance=p, clinic=request.user.clinic, lang=request.lang)
    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False)
        if "phone" in form.changed_data and obj.telegram_chat_id:
            # Bot faqat registrdagi raqam egasiga ochiladi: raqam o'zgarsa eski Telegram ulanishi uziladi
            obj.telegram_chat_id = None
            messages.info(request, "Telefon raqami o'zgardi — Telegram bot ulanishi uzildi. Ona yangi raqam bilan qayta ulanadi.")
        if obj.consent and not obj.consent_at:
            obj.consent_at = date.today()
        obj.save()
        AccessLog.log(request, obj, AccessLog.EDIT)
        messages.success(request, tr(request, "Saqlandi"))
        return redirect("patient_detail", pk=p.pk)
    return render(request, "patients/form.html", {"form": form, "title": f"{p.short_name} — {tr(request, 'tahrirlash')}"})


def _finalize_color(form, computed):
    choice = form.cleaned_data.get("color_choice", "auto")
    return computed if choice == "auto" else choice


@login_required
def visit_create(request, pk):
    p = _patient_or_404(request.user, pk)
    scope.require(scope.can_edit_clinical(request.user, p.clinic))
    initial = {"gestational_week": p.gestational_weeks, "visit_date": date.today(),
               "next_visit_date": next_anc_date(p, p.gestational_weeks)}
    form = VisitForm(request.POST or None, initial=initial, lang=request.lang)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            visit = form.save(commit=False)
            visit.patient, visit.doctor = p, request.user
            visit.source = form.cleaned_data.get("source") or "manual"
            visit.transcript = form.cleaned_data.get("transcript", "")
            try:
                visit.ai_fields = json.loads(form.cleaned_data.get("ai_fields") or "{}")
            except ValueError:
                visit.ai_fields = {}
            computed, reasons = evaluate("mother", mother_context(p, visit))
            visit.computed_color, visit.color_reasons = computed, reasons
            visit.final_color = _finalize_color(form, computed)
            if visit.final_color != computed:
                visit.color_reasons = reasons + [f"Shifokor qarori: {visit.color_override_note}"]
            visit.save()
            alert = services.apply_mother_visit(visit)
            transaction.on_commit(lambda: mother_msg.visit(visit))
            AccessLog.log(request, p, AccessLog.VISIT)
        if alert:
            msg = ("Zona yomonlashdi — OvaBMU va tuman shifokoriga avtomatik signal yuborildi." if alert.level == "ovabmu"
                   else "Zona yomonlashdi — tuman shifokoriga avtomatik signal yuborildi.")
            messages.warning(request, "⚠️ " + tr(request, msg))
        else:
            messages.success(request, tr(request, "Ko'rik tasdiqlandi va saqlandi."))
        return redirect("patient_detail", pk=p.pk)
    return render(request, "patients/visit_form.html", {
        "p": p, "form": form, "kind": "mother", "scenarios": [(k, tr(request, l)) for k, l in mock.choices("mother")],
        "preview_url": f"/risk/preview/mother/{p.pk}/",
    })


@require_POST
@login_required
def message_mother(request, pk):
    p = _patient_or_404(request.user, pk)
    text = request.POST.get("text", "").strip()
    if text:
        AccessLog.log(request, p, AccessLog.MESSAGE)
        n = services.message_mother(p, text, request.user)
        if n.status == "sent":
            messages.success(request, "Xabar onaga Telegram orqali yuborildi")
        else:
            messages.info(request, f"Xabar logga yozildi ({n.get_status_display()})")
    return redirect("patient_detail", pk=p.pk)


@login_required
@require_POST
def ai_summary(request, pk):
    """AI xulosa (HTMX): ko'riklar dinamikasi bo'yicha shifokorga qisqa tahlil. Hech narsa saqlanmaydi."""
    from apps.voice.summary import summarize
    p = _patient_or_404(request.user, pk)
    AccessLog.log(request, p, AccessLog.AI)
    res = summarize(p, getattr(request, "lang", "uz"), force=request.POST.get("force") == "1")
    return render(request, "patients/_ai_summary.html", {"p": p, "ai": res,
                                                         "can_send": scope.can_edit_clinical(request.user, p.clinic)})


@login_required
@require_POST
def ai_summary_send(request, pk):
    """Shifokor tekshirgan (kerak bo'lsa tahrirlagan) xotirjam xulosani onaga botda yuboradi."""
    from apps.alerts.mother import esc
    from apps.bot import sender
    from apps.voice.summary import alarming_words
    p = _patient_or_404(request.user, pk)
    scope.require(scope.can_edit_clinical(request.user, p.clinic))
    text = request.POST.get("text", "").strip()[:3500]
    flags = alarming_words(text)
    if not text or flags:
        return render(request, "patients/_ai_send_result.html", {"ok": False, "flags": flags, "empty": not text})
    u = request.user
    body = (f"🩺 <b>Ko'rik natijalari bo'yicha shifokor xulosasi</b>\n"
            f"👩‍⚕️ {esc(u.full_name or u.username)}, {esc(p.clinic.name)}\n\n{esc(text)}")
    n = sender.send(p.telegram_chat_id, body, kind="doctor_msg", recipient_label=f"{p.short_name} (ona)", patient=p)
    AccessLog.log(request, p, AccessLog.MESSAGE)
    return render(request, "patients/_ai_send_result.html", {"ok": True, "n": n})
