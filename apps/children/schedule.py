"""Chaqaloqni poliklinikada kuzatish rejasi (1 yoshgacha).

- Patronaj: tug'ruqxonadan chiqqach dastlabki kunlarda uyda (kindik yarasi, emizish).
- Oylik rejali ko'rik: 1 yoshgacha har oy (vazn, bo'y, bosh va ko'krak aylanasi, rivojlanish).
- Tor mutaxassislar: 1, 3, 6 oylik va 1 yoshda — nevropatolog, ortoped-jarroh, oftalmolog, LOR.
- Laboratoriya: 3–6 oylik va 1 yoshda umumiy qon va siydik tahlili; eshitish va tug'ma kasalliklar skriningi.
"""
from datetime import date, timedelta

SPECIALISTS = ["Nevropatolog", "Ortoped-jarroh", "Oftalmolog", "LOR"]
SPECIALIST_MONTHS = {1, 3, 6, 12}
LAB_MONTHS = {3, 6, 12}
MONTH_DAYS = 30.44


def month_date(birth, m):
    return birth + timedelta(days=round(m * MONTH_DAYS))


def child_plan(child, visits=None):
    visits = visits if visits is not None else list(child.visits.all())
    vdates = [v.visit_date for v in visits]
    today = date.today()
    items = [{"key": "patronage", "date": child.birth_date + timedelta(days=3), "label": "Patronaj (uyda)",
              "extra": "Kindik yarasi, emizish, umumiy holat; eshitish va tug'ma kasalliklar skriningi"}]
    for m in range(1, 13):
        extra = []
        if m in SPECIALIST_MONTHS:
            extra.append("Tor mutaxassislar: " + ", ".join(SPECIALISTS))
        if m in LAB_MONTHS:
            extra.append("Umumiy qon va siydik tahlili")
        items.append({"key": f"m{m}", "date": month_date(child.birth_date, m), "label": f"{m} oylik ko'rik",
                      "extra": "; ".join(extra)})
    for it in items:
        window = 4 if it["key"] == "patronage" else 12
        done = any(abs((d - it["date"]).days) <= window for d in vdates)
        if done:
            it["status"] = "done"
        elif it["date"] + timedelta(days=10) < today:
            it["status"] = "missed"
        elif it["date"] <= today + timedelta(days=7):
            it["status"] = "due"
        else:
            it["status"] = "upcoming"
    return items


def next_plan_date(child, after=None):
    after = after or date.today()
    for it in child_plan(child, visits=[]):
        if it["date"] > after:
            return it["date"]
    return after + timedelta(days=90)
