"""Xom ma'lumotdan ko'rsatkichlar va hudud ranglari (qo'lda hisobot kerak emas)."""
from datetime import date

from django.db.models import Case, Count, IntegerField, Min, Q, When

from apps.alerts.models import Alert, Referral
from apps.children.models import Child, ChildVaccination
from apps.patients.models import Patient
from apps.risk.engine import load_rules, region_color

ACTIVE_PATIENT = Q(status=Patient.PREGNANT)
COLOR_RANK = Case(When(current_color="red", then=2), When(current_color="yellow", then=1), default=0,
                  output_field=IntegerField())
CHILD_MAX_DAYS = 2 * 365  # 2 yoshgacha bolalar kuzatuvda (16 oylik revaksinatsiyagacha)


def active_patients(qs=None):
    return (qs if qs is not None else Patient.objects.all()).filter(ACTIVE_PATIENT)


def active_children(qs=None):
    from datetime import timedelta
    qs = qs if qs is not None else Child.objects.all()
    return qs.filter(birth_date__gte=date.today() - timedelta(days=CHILD_MAX_DAYS))


def _agg(qs, key):
    rows = qs.values(key).annotate(
        total=Count("id"),
        red=Count("id", filter=Q(current_color="red")),
        yellow=Count("id", filter=Q(current_color="yellow")),
    )
    return {r[key]: r for r in rows}


def grouped(patients_qs, children_qs, level):
    """level: 'district' | 'clinic' | 'mavze'. Har guruh uchun sonlar va rang."""
    pkey = {"district": "mavze__clinic__district", "clinic": "mavze__clinic", "mavze": "mavze"}[level]
    ckey = "mother__" + pkey
    p = _agg(active_patients(patients_qs), pkey)
    c = _agg(active_children(children_qs), ckey)
    include_children = load_rules()["region"].get("include_children", True)
    out = {}
    for k in set(p) | set(c):
        pr, cr = p.get(k, {}), c.get(k, {})
        d = {
            "p_total": pr.get("total", 0), "p_red": pr.get("red", 0), "p_yellow": pr.get("yellow", 0),
            "c_total": cr.get("total", 0), "c_red": cr.get("red", 0), "c_yellow": cr.get("yellow", 0),
        }
        d["p_green"] = d["p_total"] - d["p_red"] - d["p_yellow"]
        d["c_green"] = d["c_total"] - d["c_red"] - d["c_yellow"]
        total = d["p_total"] + (d["c_total"] if include_children else 0)
        red = d["p_red"] + (d["c_red"] if include_children else 0)
        d["total"], d["red"] = total, red
        d["red_pct"] = round(red / total * 100, 1) if total else 0
        d["color"] = region_color(red, total)
        out[k] = d
    return out


def summary(patients_qs, children_qs, alerts_qs, referrals_qs):
    """Tanlangan hudud bo'yicha KPI'lar."""
    pts = active_patients(patients_qs)
    chs = active_children(children_qs)
    today = date.today()
    p = pts.aggregate(
        total=Count("id"), red=Count("id", filter=Q(current_color="red")),
        yellow=Count("id", filter=Q(current_color="yellow")),
        missed=Count("id", filter=Q(next_visit_date__lt=today)),
    )
    c = chs.aggregate(total=Count("id"), red=Count("id", filter=Q(current_color="red")),
                      yellow=Count("id", filter=Q(current_color="yellow")))
    reg = pts.annotate(first_wk=Min("visits__gestational_week")).aggregate(
        known=Count("id", filter=Q(first_wk__isnull=False)), early=Count("id", filter=Q(first_wk__lte=12)))
    vacc = ChildVaccination.objects.filter(child__in=chs, due_date__lte=today).aggregate(
        done=Count("id", filter=Q(status="done")), overdue=Count("id", filter=Q(status="overdue")))
    due = vacc["done"] + vacc["overdue"]
    include_children = load_rules()["region"].get("include_children", True)
    total = p["total"] + (c["total"] if include_children else 0)
    red = p["red"] + (c["red"] if include_children else 0)
    return {
        "p": {**p, "green": p["total"] - p["red"] - p["yellow"]},
        "c": {**c, "green": c["total"] - c["red"] - c["yellow"]},
        "attendance_pct": round((1 - p["missed"] / p["total"]) * 100, 1) if p["total"] else 100,
        "early_reg_pct": round(reg["early"] / reg["known"] * 100, 1) if reg["known"] else 0,
        "vacc_pct": round(vacc["done"] / due * 100, 1) if due else 100,
        "vacc_overdue": vacc["overdue"],
        "alerts_open": alerts_qs.exclude(status=Alert.RESOLVED).count(),
        "alerts_new": alerts_qs.filter(status=Alert.NEW).count(),
        "referrals_open": referrals_qs.exclude(status=Referral.ACTED).count(),
        "region_color": region_color(red, total),
        "red_pct": round(red / total * 100, 1) if total else 0,
    }
