from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.accounts import scope
from apps.accounts.i18n import tr
from apps.accounts.models import User
from apps.bot import sender
from apps.children.models import Child
from apps.patients.models import Patient
from apps.risk.engine import COLOR_LABEL

from . import mother as mother_msg
from . import services
from .models import Alert, Notification, Referral


def _alerts(user):
    return scope.alerts_for(user, Alert.objects.select_related("patient", "child__mother", "clinic", "district"))


@login_required
def alert_list(request):
    qs = _alerts(request.user)
    status = request.GET.get("status", "open")
    if status == "open":
        qs = qs.exclude(status=Alert.RESOLVED)
    elif status != "all":
        qs = qs.filter(status=status)
    all_alerts = _alerts(request.user)
    alerts = mother_msg.attach(qs[:200], "alert")
    for a in alerts:
        a.can_resolve = scope.can_resolve_alert(request.user, a)
    return render(request, "alerts/list.html", {"alerts": alerts, "status": status,
                                                "metrics": alert_metrics(all_alerts),
                                                "mstats": mother_msg.stats("alert", all_alerts.values_list("id", flat=True)),
                                                "action_choices": Alert.ACTION_CHOICES})


def alert_metrics(qs):
    """O'lchanadigan natija: javob vaqti, yopilish vaqti, chora turlari, eskalatsiya ulushi."""
    from django.db.models import Avg, Count, DurationField, ExpressionWrapper, F, Q

    agg = qs.aggregate(
        total=Count("id"), seen=Count("id", filter=Q(seen_at__isnull=False)),
        resolved=Count("id", filter=Q(status=Alert.RESOLVED)), escalated=Count("id", filter=Q(escalated=True)),
        red=Count("id", filter=Q(to_color="red")),
        resp=Avg(ExpressionWrapper(F("seen_at") - F("created_at"), output_field=DurationField()),
                 filter=Q(seen_at__isnull=False)),
        close=Avg(ExpressionWrapper(F("resolved_at") - F("created_at"), output_field=DurationField()),
                  filter=Q(resolved_at__isnull=False)),
    )
    by_action = dict(qs.filter(status=Alert.RESOLVED).values_list("action_type").annotate(n=Count("id")))
    resolved = agg["resolved"] or 0
    actions = [{"key": k, "label": l, "n": by_action.get(k, 0),
                "pct": round(by_action.get(k, 0) / resolved * 100, 1) if resolved else 0} for k, l in Alert.ACTION_CHOICES]
    red_resolved = qs.filter(status=Alert.RESOLVED, to_color="red")
    red_hosp = red_resolved.filter(action_type__in=["hospital", "order"]).count()
    return {
        **agg,
        "resp_min": round(agg["resp"].total_seconds() / 60) if agg["resp"] else None,
        "close_hours": round(agg["close"].total_seconds() / 3600, 1) if agg["close"] else None,
        "escalated_pct": round(agg["escalated"] / agg["total"] * 100, 1) if agg["total"] else 0,
        "resolved_pct": round(resolved / agg["total"] * 100, 1) if agg["total"] else 0,
        "red_hosp_pct": round(red_hosp / red_resolved.count() * 100, 1) if red_resolved.count() else 0,
        "actions": actions,
    }


@login_required
def alert_panel(request):
    """HTMX: dashboard'dagi jonli signal paneli."""
    qs = _alerts(request.user).exclude(status=Alert.RESOLVED)[:6]
    return render(request, "alerts/_panel.html", {"alerts": qs})


@login_required
def alert_feed(request):
    """JS: yangi signal paydo bo'lsa toast + ovoz."""
    since = int(request.GET.get("since") or 0)
    qs = _alerts(request.user)
    new = qs.filter(id__gt=since).order_by("id")[:5] if since else []
    latest = qs.order_by("-id").values_list("id", flat=True).first() or 0
    return JsonResponse({
        "latest": latest,
        "new_count": qs.filter(status=Alert.NEW).count(),
        "items": [{
            "id": a.id, "color": a.to_color, "color_label": COLOR_LABEL[a.to_color],
            "name": a.subject_name, "kind": a.subject_kind, "clinic": a.clinic.name, "district": a.district.name,
            "reasons": a.reasons[:3], "changes": a.changes, "url": a.subject_url, "escalated": a.escalated,
        } for a in new],
    })


@require_POST
@login_required
def alert_seen(request, pk):
    # Signalga faqat yuqori bosqich (tuman / OvaBMU) javob beradi — poliklinika faqat ko'radi
    scope.require(request.user.role != User.CLINIC)
    a = get_object_or_404(_alerts(request.user), pk=pk)
    services.mark_seen(a, request.user)
    if request.headers.get("HX-Request"):
        return alert_panel(request)
    return redirect(request.POST.get("next") or "alert_list")


@require_POST
@login_required
def alert_resolve(request, pk):
    # chorani oilaviy shifokor (o'z poliklinikasi), tuman yoki OvaBMU yozishi mumkin — natija onaga boradi
    a = get_object_or_404(_alerts(request.user), pk=pk)
    scope.require(scope.can_resolve_alert(request.user, a))
    action = request.POST.get("action_type", "")
    note = request.POST.get("note", "").strip()
    if action not in dict(Alert.ACTION_CHOICES) or (action == "other" and not note):
        messages.error(request, tr(request, "Chora turini tanlang (\"Boshqa\" uchun izoh yozing)"))
        return redirect(request.POST.get("next") or "alert_list")
    services.resolve(a, request.user, note, action)
    mother_msg.action(a)
    messages.success(request, tr(request, "Signal yopildi: chora ko'rildi"))
    return redirect(request.POST.get("next") or "alert_list")


# ---------- Yo'llanmalar ----------

@login_required
def referral_list(request):
    qs = scope.referrals_for(request.user, Referral.objects.select_related("patient", "child__mother", "clinic",
                                                                         "from_user"))
    return render(request, "alerts/referrals.html", {"referrals": mother_msg.attach(qs[:200], "referral")})


@require_POST
@login_required
def referral_create(request):
    u = request.user
    scope.require(scope.can_refer(u))
    child = patient = None
    if cid := request.POST.get("child"):
        child = get_object_or_404(scope.children_for(u, Child.objects.all()), pk=cid)
        mavze = child.mother.mavze
    else:
        patient = get_object_or_404(scope.patients_for(u, Patient.objects.all()), pk=request.POST.get("patient"))
        mavze = patient.mavze
    to_level = request.POST.get("to_level", Referral.DISTRICT)
    if u.role == User.CLINIC and to_level not in (Referral.DISTRICT, Referral.OVABMU):
        to_level = Referral.DISTRICT
    r = Referral.objects.create(patient=patient or child.mother, child=child, district=mavze.clinic.district,
                                clinic=mavze.clinic, from_user=u, to_level=to_level,
                                reason=request.POST.get("reason", "").strip() or "—")
    mother_msg.referral(r, "issued")
    messages.success(request, "Yo'llanma berildi, holati kuzatilmoqda")
    return redirect(r.subject_url)


@require_POST
@login_required
def referral_status(request, pk):
    r = get_object_or_404(scope.referrals_for(request.user, Referral.objects.all()), pk=pk)
    action = request.POST.get("action")
    if request.user.role == User.CLINIC:
        messages.error(request, "Yo'llanmani qabul qiluvchi bosqich belgilaydi")
    elif action == "accept" and r.status == Referral.ISSUED:
        r.status, r.accepted_at, r.accepted_by = Referral.ACCEPTED, timezone.now(), request.user
        r.save()
    elif action == "act" and r.status in (Referral.ISSUED, Referral.ACCEPTED):
        r.status, r.acted_at = Referral.ACTED, timezone.now()
        r.accepted_at = r.accepted_at or r.acted_at
        r.accepted_by = r.accepted_by or request.user
        r.action_note = request.POST.get("note", "").strip()
        r.save()
        mother_msg.referral(r, "acted")
    return redirect(request.POST.get("next") or "referral_list")


@login_required
def notification_log(request):
    """Onalarga ketgan xabarlar: 2 ta jadval (Xabarlar / Ona tasdiqlari), filtr va sahifalash."""
    from datetime import timedelta

    import html

    from django.core.paginator import Paginator
    from django.utils.html import strip_tags
    from django.db.models import Q

    from .models import MotherConfirmation
    u = request.user
    pts = scope.patients_for(u, Patient.objects.all())
    whole_city = u.role == User.OVABMU and not scope.view_district_id(u) and not scope.view_clinic_id(u)
    tab = request.GET.get("tab", "msg")
    q = request.GET.get("q", "").strip()
    period = request.GET.get("period", "30")
    since = {"1": 1, "7": 7, "30": 30}.get(period)

    def by_q(qs):
        for w in q.split():
            qs = qs.filter(Q(patient__last_name__icontains=w) | Q(patient__first_name__icontains=w) |
                           Q(patient__phone__icontains=w))
        return qs

    msgs = Notification.objects.select_related("patient__mavze__clinic")
    if not whole_city:
        msgs = msgs.filter(patient__in=pts)
    mcs = MotherConfirmation.objects.filter(patient__in=pts).select_related("patient__mavze__clinic", "author")
    if since:
        t0 = timezone.now() - timedelta(days=since)
        msgs, mcs = msgs.filter(created_at__gte=t0), mcs.filter(created_at__gte=t0)
    msgs, mcs = by_q(msgs), by_q(mcs)

    kpi = {"total": msgs.count(), "sent": msgs.filter(status=Notification.SENT).count(),
           "no_chat": msgs.filter(status=Notification.NO_CHAT).count(),
           "failed": msgs.filter(status__in=[Notification.FAILED, Notification.NO_TOKEN]).count(),
           "mc_total": mcs.count(), "yes": mcs.filter(confirmed=True).count(), "no": mcs.filter(confirmed=False).count()}
    kpi["wait"] = kpi["mc_total"] - kpi["yes"] - kpi["no"]

    kind, status, answer = request.GET.get("kind", ""), request.GET.get("status", ""), request.GET.get("answer", "")
    if tab == "mc":
        if kind:
            mcs = mcs.filter(kind=kind)
        if answer == "yes":
            mcs = mcs.filter(confirmed=True)
        elif answer == "no":
            mcs = mcs.filter(confirmed=False)
        elif answer == "wait":
            mcs = mcs.filter(confirmed__isnull=True)
        qs, kinds = mcs, MotherConfirmation.KIND_CHOICES
    else:
        if kind:
            msgs = msgs.filter(kind=kind)
        if status:
            msgs = msgs.filter(status=status)
        qs, kinds = msgs, [k for k in Notification.KIND_CHOICES if k[0] not in ("alert", "escalation")]
    page = Paginator(qs, 25).get_page(request.GET.get("page"))
    for n in page:
        if tab != "mc":
            lines = [x for x in html.unescape(strip_tags(n.text or "")).splitlines() if x.strip()]
            n.title = lines[0] if lines else ""
            n.rest = "\n".join(lines[1:])
    params = request.GET.copy()
    params.pop("page", None)
    return render(request, "alerts/notifications.html", {
        "page": page, "tab": tab, "kpi": kpi, "kinds": kinds, "statuses": Notification.STATUS_CHOICES,
        "q": q, "period": period, "kind": kind, "status": status, "answer": answer,
        "qs_nopage": params.urlencode(), "show_clinic": u.role != User.CLINIC,
    })


