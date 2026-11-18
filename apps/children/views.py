import json
from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.accounts import scope
from apps.accounts.models import User
from apps.accounts.i18n import tr
from apps.alerts import mother as mother_msg
from apps.alerts import services
from apps.alerts.models import Referral
from apps.dashboard.stats import COLOR_RANK, active_children
from apps.patients.models import Patient
from apps.risk.engine import child_context, evaluate
from apps.risk.recompute import recompute_child
from apps.voice import mock

from .forms import ChildForm, ChildVisitForm, VaccinationSessionForm
from .models import Child, ChildVaccination, SessionInvite, VaccinationSession, create_vaccination_plan
from .schedule import SPECIALIST_MONTHS, SPECIALISTS, child_plan, next_plan_date


def _child_or_404(user, pk):
    qs = scope.children_for(user, Child.objects.select_related("mother__mavze__clinic__district"))
    return get_object_or_404(qs, pk=pk)


@login_required
def child_list(request):
    qs = active_children(scope.children_for(request.user, Child.objects.select_related("mother__mavze__clinic")))
    if color := request.GET.get("color"):
        qs = qs.filter(current_color=color)
    if request.GET.get("vacc_overdue"):
        qs = qs.filter(vaccinations__status="overdue").distinct()
    if q := request.GET.get("q", "").strip():
        for t in q.split():
            qs = qs.filter(Q(first_name__icontains=t) | Q(mother__last_name__icontains=t)
                           | Q(mother__first_name__icontains=t))
    qs = qs.annotate(rank=COLOR_RANK).order_by("-rank", "-birth_date")
    page = Paginator(qs, 30).get_page(request.GET.get("page"))
    params = request.GET.copy()
    params.pop("page", None)
    return render(request, "children/list.html", {"page": page, "params": params.urlencode(),
                                                  "total": page.paginator.count})


@login_required
def child_detail(request, pk):
    c = _child_or_404(request.user, pk)
    visits = mother_msg.attach(c.visits.select_related("doctor"), "child_visit")
    chart_visits = [v for v in reversed(visits) if v.weight]
    chart = {"labels": [c.birth_date.strftime("%d.%m")] + [v.visit_date.strftime("%d.%m") for v in chart_visits],
             "weight": [c.birth_weight] + [v.weight for v in chart_visits]}
    return render(request, "children/detail.html", {
        "c": c, "visits": visits, "chart": chart, "plan": child_plan(c, visits) if c.age_days < 400 else [],
        "vaccinations": c.vaccinations.select_related("vaccine"),
        "alerts": mother_msg.attach(c.alerts.all()[:10], "alert"), "referrals": c.referrals.all(),
        "can_edit": scope.can_edit_child(request.user, c.mother.clinic),
        "can_vacc": scope.can_vaccinate(request.user, c.mother.clinic),
        "can_refer": scope.can_refer(request.user),
        "responsible": User.objects.filter(role="clinic", clinic=c.mother.clinic, is_active=True,
                                           clinic_role__in=["ped", "nurse"]).order_by("clinic_role"),
        "referral_levels": Referral.LEVEL_CHOICES, "today": date.today(),
    })


@login_required
def child_create(request, mother_pk):
    mother = get_object_or_404(scope.patients_for(request.user, Patient.objects.all()), pk=mother_pk)
    scope.require(scope.can_edit_child(request.user, mother.clinic) or scope.can_edit_clinical(request.user, mother.clinic))
    form = ChildForm(request.POST or None, initial={"birth_date": date.today()}, lang=request.lang)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            child = form.save(commit=False)
            child.mother = mother
            child.next_visit_date = child.birth_date + timezone.timedelta(days=3)
            child.save()
            create_vaccination_plan(child)
            if mother.status == Patient.PREGNANT:
                mother.status, mother.delivered_at = Patient.DELIVERED, child.birth_date
                mother.save(update_fields=["status", "delivered_at"])
            recompute_child(child)
        messages.success(request, f"{child.full_name} qayd etildi, emlash kalendari avtomatik tuzildi.")
        return redirect("child_detail", pk=child.pk)
    title = tr(request, "Tug'ruqni qayd etish") + " — " + mother.short_name
    return render(request, "patients/form.html", {"form": form, "title": title})


@login_required
def child_visit_create(request, pk):
    c = _child_or_404(request.user, pk)
    scope.require(scope.can_edit_child(request.user, c.mother.clinic))
    age_m = round(c.age_days / 30.44)
    form = ChildVisitForm(request.POST or None, initial={
        "visit_date": date.today(), "next_visit_date": next_plan_date(c),
        "visit_type": "patronage" if c.age_days <= 10 else "monthly",
        "specialists_seen": list(SPECIALISTS) if age_m in SPECIALIST_MONTHS else []}, lang=request.lang)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            visit = form.save(commit=False)
            visit.child, visit.doctor = c, request.user
            visit.specialists = [f"{sp}: ko'rikdan o'tdi" for sp in form.cleaned_data.get("specialists_seen", [])]
            visit.source = form.cleaned_data.get("source") or "manual"
            visit.transcript = form.cleaned_data.get("transcript", "")
            try:
                visit.ai_fields = json.loads(form.cleaned_data.get("ai_fields") or "{}")
            except ValueError:
                visit.ai_fields = {}
            computed, reasons = evaluate("child", child_context(c, visit))
            visit.computed_color, visit.color_reasons = computed, reasons
            choice = form.cleaned_data.get("color_choice", "auto")
            visit.final_color = computed if choice == "auto" else choice
            if visit.final_color != computed:
                visit.color_reasons = reasons + [f"Shifokor qarori: {visit.color_override_note}"]
            visit.save()
            alert = services.apply_child_visit(visit)
            transaction.on_commit(lambda: mother_msg.child_visit(visit))
        if alert:
            msg = ("Zona yomonlashdi — OvaBMU va tuman shifokoriga avtomatik signal yuborildi." if alert.level == "ovabmu"
                   else "Zona yomonlashdi — tuman shifokoriga avtomatik signal yuborildi.")
            messages.warning(request, "⚠️ " + tr(request, msg))
        else:
            messages.success(request, tr(request, "Ko'rik tasdiqlandi va saqlandi."))
        return redirect("child_detail", pk=c.pk)
    return render(request, "patients/visit_form.html", {
        "c": c, "form": form, "kind": "child", "scenarios": [(k, tr(request, l)) for k, l in mock.choices("child")],
        "preview_url": f"/risk/preview/child/{c.pk}/",
    })


@require_POST
@login_required
def vaccination_done(request, pk):
    v = get_object_or_404(ChildVaccination.objects.select_related("child__mother__mavze__clinic", "vaccine"), pk=pk)
    _child_or_404(request.user, v.child_id)
    scope.require(scope.can_vaccinate(request.user, v.child.mother.clinic))
    # Milliy qoida: isitma yoki o'tkir kasallik bo'lsa emlash sog'ayguncha kechiktiriladi
    recent = v.child.visits.filter(visit_date__gte=date.today() - timezone.timedelta(days=3)).first()
    if recent and not request.POST.get("force") and (
            (recent.temperature and recent.temperature >= 37.5) or recent.breathing_problem or recent.final_color == "red"):
        messages.error(request, f"{v.vaccine.code}: oxirgi ko'rikda isitma / o'tkir kasallik belgisi bor "
                                f"({recent.visit_date:%d.%m}). Milliy qoidaga ko'ra emlash bola sog'ayguncha kechiktiriladi.")
        return redirect("child_detail", pk=v.child_id)
    v.status, v.done_date, v.done_by = ChildVaccination.DONE, date.fromisoformat(
        request.POST.get("done_date") or date.today().isoformat()), request.user
    v.batch = request.POST.get("batch", "")[:50]
    v.save()
    recompute_child(v.child)
    services.notify_vaccination_done(v)
    messages.success(request, f"{v.vaccine.code} emlashi bajarildi. Onaga parvarish bo'yicha eslatma yuborildi.")
    return redirect("child_detail", pk=v.child_id)


# ------------------------------------------------------------------ Emlash e'lonlari

def _sessions_for(user):
    qs = VaccinationSession.objects.select_related("clinic__district", "vaccine", "created_by")
    if user.role == "clinic":
        return qs.filter(clinic=user.clinic)
    if vc := scope.view_clinic_id(user):
        qs = qs.filter(clinic_id=vc)
    if user.role == "district":
        return qs.filter(clinic__district=user.district)
    if vd := scope.view_district_id(user):
        return qs.filter(clinic__district_id=vd)
    return qs


@login_required
def session_list(request):
    from django.db.models import Count, Q
    qs = _sessions_for(request.user).annotate(
        n=Count("invites"), n_att=Count("invites", filter=Q(invites__attended=True)),
        n_r3=Count("invites", filter=Q(invites__reminder3_at__isnull=False)),
        n_r1=Count("invites", filter=Q(invites__reminder1_at__isnull=False)))
    today = date.today()
    return render(request, "children/sessions.html", {
        "upcoming": qs.filter(date__gte=today, status="planned").order_by("date", "time"),
        "past": qs.exclude(date__gte=today, status="planned")[:50], "today": today,
    })


@login_required
def session_create(request):
    scope.require(scope.can_vaccinate(request.user, request.user.clinic))
    from .sessions import invite_eligible, send_reminders
    form = VaccinationSessionForm(request.POST or None, lang=request.lang,
                                  initial={"date": date.today() + timezone.timedelta(days=5), "time": "09:00"})
    preview = None
    if form.is_bound and form.is_valid():
        from .models import eligible_children
        if "preview" in request.POST:
            preview = list(eligible_children(request.user.clinic, form.cleaned_data["vaccine"], form.cleaned_data["date"]))
        else:
            s = form.save(commit=False)
            s.clinic, s.created_by = request.user.clinic, request.user
            s.save()
            n = invite_eligible(s)
            send_reminders()  # 3 kundan kam qolgan bo'lsa — eslatma darhol ketadi
            messages.success(request, f"{tr(request, "Emlash e'loni yaratildi")}: {n}")
            return redirect("session_detail", pk=s.pk)
    return render(request, "children/session_form.html", {"form": form, "preview": preview})


@login_required
def session_detail(request, pk):
    s = get_object_or_404(_sessions_for(request.user), pk=pk)
    invites = list(s.invites.select_related("child__mother__mavze", "vaccination").order_by("child__birth_date"))
    can_edit = scope.can_vaccinate(request.user, s.clinic)
    return render(request, "children/session_detail.html", {"s": s, "invites": invites, "can_edit": can_edit})


@require_POST
@login_required
def session_attend(request, pk):
    s = get_object_or_404(_sessions_for(request.user), pk=pk)
    scope.require(scope.can_vaccinate(request.user, s.clinic))
    ids = [int(x) for x in request.POST.getlist("invite")]
    done = 0
    for inv in s.invites.filter(id__in=ids, attended=False).select_related("vaccination__vaccine", "child__mother__mavze__clinic"):
        v = inv.vaccination
        if v.status != ChildVaccination.DONE:
            v.status, v.done_date, v.done_by = ChildVaccination.DONE, s.date if s.date <= date.today() else date.today(), request.user
            v.save()
            recompute_child(inv.child)
            services.notify_vaccination_done(v)
        inv.attended = True
        inv.save(update_fields=["attended"])
        done += 1
    if request.POST.get("finish"):
        s.status = VaccinationSession.DONE
        s.save(update_fields=["status"])
    messages.success(request, f"{tr(request, 'Emlandi deb belgilandi')}: {done}")
    return redirect("session_detail", pk=s.pk)


@require_POST
@login_required
def session_cancel(request, pk):
    s = get_object_or_404(_sessions_for(request.user), pk=pk)
    scope.require(scope.can_vaccinate(request.user, s.clinic))
    s.status = VaccinationSession.CANCELLED
    s.save(update_fields=["status"])
    messages.info(request, tr(request, "E'lon bekor qilindi"))
    return redirect("session_list")
