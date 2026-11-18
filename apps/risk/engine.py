"""Rang zonasi hisoblash: bemor (ona/chaqaloq) va hudud darajasida.

Qoidalar rules.json faylida saqlanadi — kod o'zgarmasdan chegaralarni almashtirish mumkin.
"""
import json
from datetime import date

from django.conf import settings
from django.utils import timezone

from apps.patients.models import GREEN, RED, YELLOW

COLOR_ORDER = {GREEN: 0, YELLOW: 1, RED: 2}
COLOR_LABEL = {GREEN: "Yashil", YELLOW: "Sariq", RED: "Qizil"}
COLOR_EMOJI = {GREEN: "🟢", YELLOW: "🟡", RED: "🔴"}

_cache = {"mtime": None, "rules": None}


def load_rules():
    path = settings.RULES_FILE
    mtime = path.stat().st_mtime
    if _cache["mtime"] != mtime:
        with open(path, encoding="utf-8") as f:
            _cache["rules"] = json.load(f)
        _cache["mtime"] = mtime
    return _cache["rules"]


def _check(cond, ctx):
    field, op, value = cond
    actual = ctx.get(field)
    if actual is None or actual == "":
        return False  # aytilmagan / o'lchanmagan qiymat hech qachon xavf deb hisoblanmaydi
    try:
        if op == "==":
            return actual == value
        if op == "in":
            return actual in value
        actual = float(actual)
        if op == ">=":
            return actual >= value
        if op == ">":
            return actual > value
        if op == "<=":
            return actual <= value
        if op == "<":
            return actual < value
    except (TypeError, ValueError):
        return False
    raise ValueError(f"Noma'lum operator: {op}")


def _matches(rule, ctx):
    if "all" in rule:
        return all(_check(c, ctx) for c in rule["all"])
    return any(_check(c, ctx) for c in rule["any"])


def evaluate(kind, ctx):
    """kind: 'mother' | 'child'. Qaytaradi: (rang, [sabablar])."""
    rules = load_rules()[kind]
    red = [r["label"] for r in rules["red"] if _matches(r, ctx)]
    yellow = [r["label"] for r in rules["yellow"] if _matches(r, ctx)]
    if red:
        return RED, red + yellow
    if yellow:
        return YELLOW, yellow
    return GREEN, []


def worse(a, b):
    """b rang a dan yomonroqmi?"""
    return COLOR_ORDER[b] > COLOR_ORDER[a]


# ---------- Kontekst yig'ish ----------

def mother_context(patient, visit=None):
    """Ona uchun qoidalar konteksti: oxirgi ko'rik tahlillari + bemor ma'lumotlari."""
    ctx = {
        "age": patient.age,
        "has_prev_complications": bool(patient.previous_complications.strip()),
        "missed_visit": patient.missed_visit,
    }
    if visit is not None:
        for f in ["bp_sys", "bp_dia", "hb", "urine_protein", "fetal_movement", "fetal_heart_rate",
                  "edema", "bleeding", "headache_vision"]:
            ctx[f] = getattr(visit, f)
        ctx["temperature"] = float(visit.temperature) if visit.temperature is not None else None
        ctx["bp_high"] = bool((visit.bp_sys or 0) >= 140 or (visit.bp_dia or 0) >= 90)
        if visit.next_visit_date and visit.next_visit_date >= date.today():
            ctx["missed_visit"] = False
    return ctx


def child_context(child, visit=None):
    overdue = child.vaccinations.filter(status="overdue").count()
    ctx = {
        "birth_weight": child.birth_weight,
        "gestational_age_at_birth": child.gestational_age_at_birth,
        "apgar_5": child.apgar_5,
        "age_days": child.age_days,
        "overdue_vaccines": overdue,
        "missed_visit": bool(child.next_visit_date and child.next_visit_date < date.today()),
    }
    if visit is not None:
        for f in ["feeding", "jaundice", "breathing_problem", "convulsions"]:
            ctx[f] = getattr(visit, f)
        ctx["temperature"] = float(visit.temperature) if visit.temperature is not None else None
        # yangi tug'ilganlarda (≤ 14 kun) tug'ilgandagi vazndan yo'qotish foizi
        if visit.weight and child.birth_weight and (visit.visit_date - child.birth_date).days <= 14:
            ctx["weight_loss_pct"] = round((child.birth_weight - visit.weight) / child.birth_weight * 100, 1)
        if visit.next_visit_date and visit.next_visit_date >= date.today():
            ctx["missed_visit"] = False
    return ctx


# ---------- Hudud rangi ----------

def region_color(red, total):
    if not total:
        return "none"
    cfg = load_rules()["region"]
    share = red / total
    if share >= cfg["red_from"]:
        return RED
    if share >= cfg["yellow_from"]:
        return YELLOW
    return GREEN


def now():
    return timezone.now()
