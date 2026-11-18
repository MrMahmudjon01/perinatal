"""Homiladorlar uchun tahlil va ko'rik ko'rsatkichlarining me'yorlari (min / max / og'irlik darajalari).

Chegaralar rules.json (zona qoidalari) bilan bir xil — bitta haqiqat manbai bo'lishi uchun.
Manbalar: JSST antenatal tavsiyalari (2016), JSST gemoglobin chegaralari (2011, 2024),
ISSHP/ACOG gipertenziya tasnifi, FIGO homila yurak urishi me'yori, O'zbekiston SSV antenatal standarti.
"""
from decimal import Decimal

# status: normal | low | high ; level: 0 me'yor, 1 e'tibor, 2 jiddiy
NORMS = {
    "hb": {
        "label": "Gemoglobin", "unit": "g/l", "min": 110, "max": None,
        "norm": "≥110 g/l",
        "bands": [(70, "low", 2, "og'ir anemiya (<70)"), (100, "low", 1, "o'rtacha anemiya (70–99)"),
                  (110, "low", 1, "yengil anemiya (100–109)")],
        "source": "JSST, 2011/2024",
    },
    "bp_sys": {
        "label": "Sistolik qon bosimi", "unit": "mm sim. ust.", "min": 90, "max": 139,
        "norm": "90–139",
        "bands_high": [(160, 2, "og'ir gipertenziya (≥160)"), (140, 1, "gipertenziya (140–159)")],
        "bands": [(90, "low", 1, "past qon bosimi (<90)")],
        "source": "ISSHP 2021 / ACOG",
    },
    "bp_dia": {
        "label": "Diastolik qon bosimi", "unit": "mm sim. ust.", "min": 60, "max": 89,
        "norm": "60–89",
        "bands_high": [(110, 2, "og'ir gipertenziya (≥110)"), (90, 1, "gipertenziya (90–109)")],
        "bands": [(60, "low", 1, "past (<60)")],
        "source": "ISSHP 2021 / ACOG",
    },
    "fetal_heart_rate": {
        "label": "Homila yurak urishi", "unit": "1 daq.", "min": 110, "max": 160,
        "norm": "110–160",
        "bands_high": [(161, 2, "taxikardiya (>160)")],
        "bands": [(110, "low", 2, "bradikardiya (<110)")],
        "source": "FIGO 2015",
    },
    "temperature": {
        "label": "Harorat", "unit": "°C", "min": 36.0, "max": 37.4,
        "norm": "36,0–37,4",
        "bands_high": [(38.5, 2, "yuqori harorat (≥38,5)"), (37.5, 1, "subfebril (37,5–38,4)")],
        "bands": [(36.0, "low", 1, "past harorat (<36,0)")],
        "source": "SSV standarti",
    },
}
PROTEIN = {"": None, "none": (0, "yo'q"), "trace": (0, "iz"), "+": (1, "+ (proteinuriya)"),
           "++": (2, "++ (proteinuriya)"), "+++": (2, "+++ (proteinuriya)")}
MOVEMENT = {"normal": (0, "normal"), "decreased": (1, "sustlashgan"), "absent": (2, "yo'q"), "na": None, "": None}


def _num(v):
    return float(v) if isinstance(v, Decimal) else v


def assess_value(field, value):
    """Bitta qiymatni me'yor bilan solishtiradi."""
    n = NORMS[field]
    value = _num(value)
    status, level, note = "normal", 0, "me'yorda"
    for thr, lvl, txt in n.get("bands_high", []):
        if value >= thr:
            status, level, note = "high", lvl, txt
            break
    if status == "normal":
        for thr, st, lvl, txt in n.get("bands", []):
            if value < thr:
                status, level, note = st, lvl, txt
                break
    return {"field": field, "label": n["label"], "value": value, "unit": n["unit"], "norm": n["norm"],
            "min": n["min"], "max": n["max"], "status": status, "level": level, "note": note, "source": n["source"]}


def assess_visit(v):
    """Ko'rikdagi barcha o'lchangan ko'rsatkichlar: qiymat, me'yor, holat."""
    rows = []
    for f in ("bp_sys", "bp_dia", "hb", "fetal_heart_rate", "temperature"):
        val = getattr(v, f, None)
        if val is not None:
            rows.append(assess_value(f, val))
    p = PROTEIN.get(v.urine_protein or "")
    if p:
        rows.append({"field": "urine_protein", "label": "Siydikda oqsil", "value": p[1], "unit": "", "norm": "yo'q / iz",
                     "min": None, "max": None, "status": "high" if p[0] else "normal", "level": p[0],
                     "note": "me'yorda" if not p[0] else "proteinuriya", "source": "ISSHP 2021"})
    m = MOVEMENT.get(v.fetal_movement or "")
    if m:
        rows.append({"field": "fetal_movement", "label": "Homila harakati", "value": m[1], "unit": "", "norm": "normal",
                     "min": None, "max": None, "status": "low" if m[0] else "normal", "level": m[0],
                     "note": "me'yorda" if not m[0] else m[1], "source": "JSST 2016"})
    return rows


def series_range(visits, field):
    """Butun kuzatuv davomida min / max qiymat va qachon bo'lgani."""
    pts = [(v.visit_date, _num(getattr(v, field))) for v in visits if getattr(v, field, None) is not None]
    if not pts:
        return None
    lo = min(pts, key=lambda x: x[1])
    hi = max(pts, key=lambda x: x[1])
    return {"min": lo[1], "min_date": lo[0], "max": hi[1], "max_date": hi[0], "n": len(pts)}
