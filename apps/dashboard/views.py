import json
from datetime import date, timedelta
from pathlib import Path

from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from apps.accounts import scope
from apps.accounts.models import User
from apps.alerts.models import Alert, Referral
from apps.children.models import Child, ChildVaccination, Vaccine
from apps.geo.models import Clinic, District, Mavze
from apps.patients.models import Patient

from . import stats

GEOJSON = Path(__file__).resolve().parents[1] / "geo" / "data" / "districts.geojson"
EMPTY = {"total": 0, "red": 0, "red_pct": 0, "color": "none", "p_total": 0, "p_red": 0, "p_yellow": 0, "p_green": 0,
         "c_total": 0, "c_red": 0, "c_yellow": 0, "c_green": 0}


def _scope_qs(user):
    pts = scope.patients_for(user, Patient.objects.all())
    chs = scope.children_for(user, Child.objects.all())
    return pts, chs, scope.alerts_for(user, Alert.objects.all()), scope.referrals_for(user, Referral.objects.all())


def _rows(objs, groups, href):
    rows = [{"obj": o, "href": href(o), **(groups.get(o.id) or EMPTY)} for o in objs]
    rows.sort(key=lambda r: (-r["red_pct"], -r["p_red"], str(r["obj"])))
    return rows


def _level_rows(user):
    """Rolga qarab keyingi daraja: OvaBMU → tumanlar, tuman → poliklinikalar, poliklinika → mavzelar."""
    pts, chs, *_ = _scope_qs(user)
    if user.role == User.CLINIC:
        return "mavze", _rows(Mavze.objects.filter(clinic=user.clinic), stats.grouped(pts, chs, "mavze"),
                              lambda o: reverse("patient_list") + f"?mavze={o.id}")
    if vc := scope.view_clinic_id(user):
        return "mavze", _rows(Mavze.objects.filter(clinic_id=vc), stats.grouped(pts, chs, "mavze"),
                              lambda o: reverse("patient_list") + f"?mavze={o.id}")
    district_id = user.district_id if user.role == User.DISTRICT else scope.view_district_id(user)
    if district_id:
        return "clinic", _rows(Clinic.objects.filter(district_id=district_id), stats.grouped(pts, chs, "clinic"),
                               lambda o: reverse("clinic_dashboard", args=[o.id]))
    return "district", _rows(District.objects.all(), stats.grouped(pts, chs, "district"),
                             lambda o: reverse("district_dashboard", args=[o.id]))


# ------------------------------------------------------------------ Umumiy ko'rinish

def _overview_ctx(user):
    pts, chs, als, refs = _scope_qs(user)
    level, rows = _level_rows(user)
    return {
        "kpi": stats.summary(pts, chs, als, refs),
        "level": level,
        "worst": [r for r in rows if r["p_total"]][:5],
        "attention": stats.active_patients(pts).filter(current_color="red")
                     .select_related("mavze__clinic").order_by("-color_updated_at")[:6],
    }


@login_required
def home(request):
    return render(request, "dashboard/overview.html", _overview_ctx(request.user))


@login_required
def overview_live(request):
    return render(request, "dashboard/_overview_live.html", _overview_ctx(request.user))


# ------------------------------------------------------------------ Hududlar

@login_required
def regions(request):
    level, rows = _level_rows(request.user)
    pts, chs, als, refs = _scope_qs(request.user)
    return render(request, "dashboard/regions.html", {"level": level, "rows": rows,
                                                      "kpi": stats.summary(pts, chs, als, refs)})


@login_required
def district_dashboard(request, pk):
    district = get_object_or_404(District, pk=pk)
    scope.require(scope.can_see_district(request.user, district))
    pts = Patient.objects.filter(mavze__clinic__district=district)
    chs = Child.objects.filter(mother__mavze__clinic__district=district)
    rows = _rows(district.clinics.all(), stats.grouped(pts, chs, "clinic"),
                 lambda o: reverse("clinic_dashboard", args=[o.id]))
    return render(request, "dashboard/district.html", {
        "district": district, "rows": rows,
        "kpi": stats.summary(pts, chs, Alert.objects.filter(district=district), Referral.objects.filter(district=district)),
    })


@login_required
def clinic_dashboard(request, pk):
    clinic = get_object_or_404(Clinic.objects.select_related("district"), pk=pk)
    scope.require(scope.can_see_clinic(request.user, clinic))
    pts = Patient.objects.filter(mavze__clinic=clinic)
    chs = Child.objects.filter(mother__mavze__clinic=clinic)
    rows = _rows(clinic.mavzes.all(), stats.grouped(pts, chs, "mavze"),
                 lambda o: reverse("patient_list") + f"?mavze={o.id}")
    return render(request, "dashboard/clinic.html", {
        "clinic": clinic, "rows": rows,
        "kpi": stats.summary(pts, chs, Alert.objects.filter(clinic=clinic), Referral.objects.filter(clinic=clinic)),
    })


# ------------------------------------------------------------------ Xarita

@login_required
def map_page(request):
    u = request.user
    scope.require(u.role in (User.OVABMU, User.DISTRICT))
    if vc := scope.view_clinic_id(u):   # xaritada mavze yo'q — tanlangan poliklinika nuqtasi ko'rsatiladi
        pts, chs, *_ = _scope_qs(u)
        level, rows = "clinic", _rows(Clinic.objects.filter(id=vc), stats.grouped(pts, chs, "clinic"),
                                      lambda o: reverse("clinic_dashboard", args=[o.id]))
    else:
        level, rows = _level_rows(u)
    return render(request, "dashboard/map.html", {"rows": rows, "level": level})


@login_required
def map_data(request):
    """Tuman chegaralari (OSM) zona rangida + poliklinikalar nuqtalari."""
    u = request.user
    scope.require(u.role in (User.OVABMU, User.DISTRICT))
    geo = json.loads(GEOJSON.read_text("utf-8"))
    districts = {d.name: d for d in District.objects.all()}
    pts, chs, *_ = _scope_qs(u)
    dg, cg = stats.grouped(pts, chs, "district"), stats.grouped(pts, chs, "clinic")
    feats = []
    for f in geo["features"]:
        d = districts.get(f["properties"]["name"])
        only = u.district_id if u.role == User.DISTRICT else scope.view_district_id(u)
        if not d or (only and d.id != only):
            continue
        g = dg.get(d.id, EMPTY)
        f["properties"].update(id=d.id, color=g["color"], red_pct=g["red_pct"], p_total=g["p_total"],
                               p_red=g["p_red"], p_yellow=g["p_yellow"], c_total=g["c_total"],
                               population=d.population, url=reverse("district_dashboard", args=[d.id]))
        feats.append(f)
    qs = Clinic.objects.select_related("district").exclude(lat=None)
    only = u.district_id if u.role == User.DISTRICT else scope.view_district_id(u)
    if only:
        qs = qs.filter(district_id=only)
    if vc := scope.view_clinic_id(u):
        qs = qs.filter(id=vc)
    clinics = [{"id": c.id, "name": c.name, "district": c.district.name, "district_id": c.district_id,
                "lat": c.lat, "lon": c.lon, "source": c.source, **{k: cg.get(c.id, EMPTY)[k] for k in
                ("color", "red_pct", "p_total", "p_red", "p_yellow", "c_total")},
                "url": reverse("clinic_dashboard", args=[c.id])} for c in qs]
    return JsonResponse({"type": "FeatureCollection", "features": feats, "clinics": clinics})


# ------------------------------------------------------------------ Emlash

@login_required
def vaccination_page(request):
    chs = stats.active_children(scope.children_for(request.user, Child.objects.all()))
    today = date.today()
    vq = ChildVaccination.objects.filter(child__in=chs)
    overdue = vq.filter(status="overdue").select_related("child__mother__mavze__clinic", "vaccine").order_by("due_date")
    week = vq.filter(status="planned", due_date__gte=today, due_date__lte=today + timedelta(days=7)) \
        .select_related("child__mother__mavze__clinic", "vaccine").order_by("due_date")
    cov = vq.filter(due_date__lte=today).values("vaccine__code", "vaccine__age_days").annotate(
        done=Count("id", filter=Q(status="done")), total=Count("id")).order_by("vaccine__age_days", "vaccine__code")
    coverage = [{"code": r["vaccine__code"], "done": r["done"], "total": r["total"],
                 "pct": round(r["done"] / r["total"] * 100, 1) if r["total"] else 0} for r in cov]
    from apps.alerts.services import missed_sent
    overdue_list = list(overdue[:100])
    sent = missed_sent({f"v:{v.id}" for v in overdue_list})
    for v in overdue_list:
        v.sent_at = sent.get(f"v:{v.id}")
    return render(request, "dashboard/vaccination.html", {
        "overdue": overdue_list, "overdue_count": overdue.count(), "week": week[:100], "week_count": week.count(),
        "coverage": coverage, "kpi_vacc": stats.summary(Patient.objects.none(), chs, Alert.objects.none(),
                                                        Referral.objects.none()),
        "today": today,
    })


# ------------------------------------------------------------------ Patronaj

def _missed_lists(user):
    today = date.today()
    pts = stats.active_patients(scope.patients_for(user, Patient.objects.all())) \
        .filter(next_visit_date__lt=today).select_related("mavze__clinic").order_by("next_visit_date")
    chs = stats.active_children(scope.children_for(user, Child.objects.all())) \
        .filter(next_visit_date__lt=today).select_related("mother__mavze__clinic").order_by("next_visit_date")
    return pts, chs


@login_required
def patronage_page(request):
    from apps.alerts.services import missed_sent
    today = date.today()
    pts, chs = _missed_lists(request.user)
    pl, cl = list(pts[:150]), list(chs[:150])
    sent = missed_sent({f"m:{p.id}" for p in pl} | {f"c:{c.id}" for c in cl})
    for p in pl:
        p.sent_at = sent.get(f"m:{p.id}")
    for c in cl:
        c.sent_at = sent.get(f"c:{c.id}")
    return render(request, "dashboard/patronage.html", {"patients": pl, "p_count": pts.count(),
                                                        "children": cl, "c_count": chs.count(), "today": today})


@login_required
def remind_missed(request):
    """Shifokor kelmaganlarga botda eslatma yuboradi: bittasiga (HTMX) yoki ro'yxatdagi hammasiga."""
    from django.contrib import messages
    from django.http import HttpResponse
    from django.views.decorators.http import require_POST  # noqa: F401
    from apps.alerts import services
    from apps.alerts.services import missed_sent
    if request.method != "POST":
        return HttpResponse(status=405)
    u, kind = request.user, request.POST.get("kind", "")
    chs_all = scope.children_for(u, Child.objects.all())
    if kind == "mother":
        qs = scope.patients_for(u, Patient.objects.select_related("mavze__clinic"))
    elif kind == "child":
        qs = chs_all.select_related("mother__mavze__clinic")
    elif kind == "vacc":
        qs = ChildVaccination.objects.filter(child__in=chs_all, status="overdue") \
            .select_related("child__mother__mavze__clinic", "vaccine")
    else:
        return HttpResponse(status=400)
    if request.POST.get("all") == "1":
        if kind == "vacc":
            objs = list(qs.order_by("due_date")[:100])
        else:
            pts, chs = _missed_lists(u)
            objs = list((pts if kind == "mother" else chs)[:150])
        tag = {"mother": "m", "child": "c", "vacc": "v"}[kind]
        done = missed_sent({f"{tag}:{o.id}" for o in objs}, days=1)
        n = 0
        for o in objs:
            if f"{tag}:{o.id}" not in done:  # bugun yuborilganlarga qayta yuborilmaydi
                services.missed_reminder(kind, o, u)
                n += 1
        messages.success(request, f"{n} ta eslatma yuborildi (bugun yuborilganlar takrorlanmadi)")
        return redirect(request.POST.get("next") or "patronage_page")
    obj = get_object_or_404(qs, pk=request.POST.get("id"))
    n = services.missed_reminder(kind, obj, u)
    icon = "check2-circle" if n.status == "sent" else "journal-check"
    title = "Telegram orqali yuborildi" if n.status == "sent" else "Bot ulanmagan — logga yozildi"
    return HttpResponse(f'<span class="small" style="color:var(--z-green)" title="{title}"><i class="bi bi-{icon}"></i> '
                        f'{timezone_now_label()}</span>')


def timezone_now_label():
    from django.utils import timezone
    return timezone.localtime().strftime("%d.%m %H:%M")


# ------------------------------------------------------------------ Statistika

ZONE_ORDER = {"green": 0, "yellow": 1, "red": 2, "none": 3}


@login_required
def stats_page(request):
    """Statistika: 1) Grafik — 2 ta oddiy grafik; 2) Reyting — hududlar yashildan qizilga tartiblangan jadval."""
    from django.db.models import Min
    u = request.user
    pts, chs, als, refs = _scope_qs(u)
    level, rows = _level_rows(u)
    rows = [r for r in rows if r["p_total"]]
    key = {"district": "mavze__clinic__district", "clinic": "mavze__clinic", "mavze": "mavze"}[level]
    active = stats.active_patients(pts)

    early = {}
    for k, fw in active.annotate(fw=Min("visits__gestational_week")).values_list(key, "fw"):
        e = early.setdefault(k, [0, 0])
        if fw is not None:
            e[0] += 1
            e[1] += fw <= 12
    missed = dict(active.filter(next_visit_date__lt=date.today()).values_list(key).annotate(n=Count("id")))
    ckey = "child__mother__" + key
    vacc = {r[ckey]: (r["done"], r["total"]) for r in ChildVaccination.objects.filter(
        child__in=stats.active_children(chs), due_date__lte=date.today())
        .values(ckey).annotate(done=Count("id", filter=Q(status="done")), total=Count("id"))}

    def pct(a, b):
        return round(a / b * 100, 1) if b else 0

    for r in rows:
        oid = r["obj"].id
        known, ok = early.get(oid, [0, 0])
        done, total = vacc.get(oid, (0, 0))
        r["early_pct"] = pct(ok, known)
        r["attend_pct"] = pct(r["p_total"] - missed.get(oid, 0), r["p_total"])
        r["vacc_pct"] = pct(done, total)
    # Reyting: yashildan qizilga (eng yaxshi tepada) — zona, keyin qizil %, keyin sariq ulushi
    rows.sort(key=lambda r: (ZONE_ORDER[r["color"]], r["red_pct"], r["p_yellow"] / max(1, r["p_total"])))
    for i, r in enumerate(rows, 1):
        r["rank"] = i

    reasons = {}
    for rs in active.filter(current_color="red").values_list("color_reasons", flat=True):
        for x in rs:
            reasons[x] = reasons.get(x, 0) + 1
    top = sorted(reasons.items(), key=lambda x: -x[1])[:6]
    chart = {"labels": [r["obj"].name for r in rows], "red_pct": [r["red_pct"] for r in rows],
             "colors": [r["color"] for r in rows],
             "reasons": [x for x, _ in top], "reason_counts": [n for _, n in top]}
    zones = {z: sum(1 for r in rows if r["color"] == z) for z in ("green", "yellow", "red")}
    return render(request, "dashboard/stats.html", {"chart": chart, "level": level, "rows": rows, "zones": zones,
                                                    "kpi": stats.summary(pts, chs, als, refs),
                                                    "tab": request.GET.get("tab", "chart")})


# ------------------------------------------------------------------ Manbalar

@login_required
def about(request):
    from apps.risk.engine import load_rules
    region = load_rules()["region"]
    total = Clinic.objects.count()
    osm = Clinic.objects.filter(source="osm").count()
    preg = stats.active_patients().count()
    return render(request, "dashboard/about.html", {
        "osm_clinics": osm, "synth_clinics": total - osm, "total_clinics": total, "vaccines": Vaccine.objects.count(),
        "red_from": int(region["red_from"] * 100), "yellow_from": int(region["yellow_from"] * 100),
        "scale_label": f"demo hajmi: {preg} homilador ≈ real hajmning ~10%",
    })


# ------------------------------------------------------------------ Dinamika (oyma-oy zona o'zgarishi)

MONTHS = {"uz": "Yan Fev Mar Apr May Iyun Iyul Avg Sen Okt Noy Dek", "ru": "Янв Фев Мар Апр Май Июн Июл Авг Сен Окт Ноя Дек",
          "en": "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec"}


@login_required
def dynamics_page(request):
    """Tuman va shahar: hududlar zonasi o'tgan oyga (3/6 oy oldinga) nisbatan qanday o'zgardi."""
    from . import history
    u = request.user
    scope.require(u.role in (User.OVABMU, User.DISTRICT))
    clinics = Clinic.objects.all()
    if vc := scope.view_clinic_id(u):
        clinics = clinics.filter(id=vc)
    elif u.role == User.DISTRICT:
        clinics = clinics.filter(district_id=u.district_id)
    elif vd := scope.view_district_id(u):
        clinics = clinics.filter(district_id=vd)
    city = u.role == User.OVABMU and not scope.view_district_id(u) and not vc
    unit = request.GET.get("unit", "district") if city else "clinic"
    if unit not in ("district", "clinic"):
        unit = "district"
    compare = int(request.GET.get("compare", "1")) if request.GET.get("compare", "1") in ("1", "3", "6") else 1
    d = history.dynamics(list(clinics.values_list("id", flat=True)), unit, months=7, compare=compare)
    names = MONTHS.get(getattr(request, "lang", "uz"), MONTHS["uz"]).split()
    label = lambda m: f"{names[m.month - 1]} {m:%y}"  # noqa: E731
    for r in d["rows"]:
        r["href"] = reverse("district_dashboard" if unit == "district" else "clinic_dashboard", args=[r["obj"].id])
    show = request.GET.get("show", "changed")
    rows = d["rows"] if show == "all" else [r for r in d["rows"] if r["change"] in ("better", "worse")]
    chart = {"labels": [label(m) for m in d["months"]], "pct": [t["pct"] for t in d["total"]],
             "green": [b["green"] for b in d["by_month"]], "yellow": [b["yellow"] for b in d["by_month"]],
             "red": [b["red"] for b in d["by_month"]]}
    return render(request, "dashboard/dynamics.html", {
        **d, "rows": rows, "all_count": len(d["rows"]), "unit": unit, "city": city, "compare": compare, "show": show,
        "chart": chart, "month_labels": [label(m) for m in d["months"]],
        "now_label": label(d["months"][-1]), "base_label": label(d["base_month"]),
    })


# ------------------------------------------------------------------ Loyiha haqida (mentorlar uchun)

@login_required
def project_page(request):
    """Muammo/yechim, biznes model, qonunchilik va xavfsizlik, ta'sir ko'rsatkichlari (jonli)."""
    from apps.alerts.views import alert_metrics
    from apps.patients.models import AccessLog
    pts, chs, als, refs = _scope_qs(request.user)
    return render(request, "dashboard/project.html", {
        "kpi": stats.summary(pts, chs, als, refs), "m": alert_metrics(als),
        "audit_n": AccessLog.objects.count(), "clinics": Clinic.objects.count(),
        "consent_pct": round(Patient.objects.filter(consent=True).count() / max(1, Patient.objects.count()) * 100),
        "tab": request.GET.get("tab", "problem"),
    })
