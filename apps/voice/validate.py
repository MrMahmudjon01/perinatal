"""AI/ovoz natijasini tekshirish: tur o'zgartirish, mantiqsiz qiymatlarni belgilash."""
from datetime import date

from apps.accounts.i18n import translate

MOTHER_RANGES = {
    "gestational_week": (4, 42), "bp_sys": (70, 230), "bp_dia": (40, 140), "hb": (40, 180),
    "fetal_heart_rate": (80, 200), "weight": (35, 160), "temperature": (34, 42),
}
CHILD_RANGES = {"weight": (500, 20000), "height": (30, 110), "temperature": (34, 42), "head_circ": (28, 56), "chest_circ": (25, 60)}

ENUMS = {
    "urine_protein": {"none", "trace", "+", "++", "+++"},
    "fetal_movement": {"normal", "decreased", "absent", "na"},
    "feeding": {"breast", "mixed", "formula", "poor"},
}
BOOLS = {"edema", "bleeding", "headache_vision", "jaundice", "breathing_problem", "convulsions"}
TEXTS = {"complaints", "complications", "diagnosis", "recommendation"}


def _to_number(v):
    if isinstance(v, (int, float)):
        return v
    if isinstance(v, str):
        from .numbers import words_to_numbers
        v = words_to_numbers(v).replace(",", ".").strip()
        try:
            f = float(v)
            return int(f) if f.is_integer() else f
        except ValueError:
            return None
    return None


def clean(kind, fields, lang="uz"):
    T = lambda x: translate(x, lang)  # noqa: E731
    """Qaytaradi: (tozalangan maydonlar, {maydon: ogohlantirish})."""
    ranges = MOTHER_RANGES if kind == "mother" else CHILD_RANGES
    out, warnings = {}, {}
    for k, v in (fields or {}).items():
        if v is None or v == "":
            continue
        if k in ranges:
            n = _to_number(v)
            if n is None:
                warnings[k] = f"{T("Raqamga aylantirib bo'lmadi")}: «{v}»"
                continue
            lo, hi = ranges[k]
            if not lo <= n <= hi:
                warnings[k] = f"{T('Mantiqsiz qiymat, tekshiring')} ({n})"
            out[k] = n
        elif k in ENUMS:
            if v in ENUMS[k]:
                out[k] = v
            else:
                warnings[k] = f"{T("Noma'lum qiymat")}: «{v}»"
        elif k in BOOLS:
            out[k] = v if isinstance(v, bool) else str(v).lower() in ("true", "ha", "bor", "1")
        elif k in TEXTS:
            out[k] = str(v).strip()
        elif k == "next_visit_date":
            try:
                d = date.fromisoformat(str(v))
                out[k] = d.isoformat()
                if d < date.today():
                    warnings[k] = T("Sana o'tib ketgan")
            except ValueError:
                warnings[k] = f"{T("Sana formati noto'g'ri")}: «{v}»"
    if kind == "mother" and out.get("bp_sys") and out.get("bp_dia") and out["bp_sys"] <= out["bp_dia"]:
        warnings["bp_sys"] = warnings["bp_dia"] = T("Sistolik bosim diastolikdan katta bo'lishi kerak")
    return out, warnings
