"""Antenatal kuzatuv rejasi — O'zR SSV bazaviy paketi: kamida 8 tashrif (manba: ishonch.org/campaign1).

12-haftagacha birinchi tashrif; 20, 26, 30, 34, 36, 38, 40-haftalar. 3 ta tashrifda skrining UTT.
"""
from datetime import date, timedelta

ANC_VISITS = [
    (12, "Birinchi tashrif: ro'yxatga olish, anamnez, tahlillar, individual reja", "1-trimestr skriningi (UTT 11–13 hafta + qon)"),
    (20, "Ikkinchi tashrif", "2-trimestr skriningi (UTT 18–20 hafta, tug'ma nuqsonlar)"),
    (26, "Uchinchi tashrif", None),
    (30, "To'rtinchi tashrif", "3-trimestr skriningi (UTT 28–32 hafta)"),
    (34, "Beshinchi tashrif", None),
    (36, "Oltinchi tashrif", None),
    (38, "Yettinchi tashrif", None),
    (40, "Sakkizinchi tashrif", None),
]
EARLY_REGISTRATION_WEEK = 12


def week_date(lmp, week):
    return lmp + timedelta(weeks=week)


def anc_plan(patient, visits=None):
    """Har bir rejali tashrif: sana, holat (done / missed / due / upcoming)."""
    if not patient.lmp_date:
        return []
    visits = visits if visits is not None else list(patient.visits.all())
    weeks = sorted({v.gestational_week for v in visits if v.gestational_week})
    today = date.today()
    plan, prev = [], 0
    for wk, label, screening in ANC_VISITS:
        lo = 0 if wk == 12 else prev + 1
        done = [w for w in weeks if lo <= w <= wk + 1]
        d = week_date(patient.lmp_date, wk)
        if done:
            status = "done"
        elif patient.status != "pregnant":
            status = "skipped"
        elif d + timedelta(days=7) < today:
            status = "missed"
        elif d <= today + timedelta(days=7):
            status = "due"
        else:
            status = "upcoming"
        plan.append({"week": wk, "date": d, "label": label, "screening": screening, "status": status,
                     "done_week": done[0] if done else None})
        prev = wk + 1
    return plan


def next_anc_date(patient, current_week):
    """Joriy haftadan keyingi rejali tashrif sanasi."""
    if not patient.lmp_date:
        return None
    for wk, *_ in ANC_VISITS:
        if wk > (current_week or 0):
            return week_date(patient.lmp_date, wk)
    return None


def registration_week(patient, visits=None):
    visits = visits if visits is not None else list(patient.visits.all())
    weeks = [v.gestational_week for v in visits if v.gestational_week]
    return min(weeks) if weeks else None
