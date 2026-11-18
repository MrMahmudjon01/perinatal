"""Matndan ko'rik maydonlarini ajratish (qoidaga asoslangan).

Mock rejimida asosiy ajratuvchi, VoiceLab rejimida LLM bo'sh qoldirgan maydonlar uchun zaxira.
Qoida: matnda aytilmagan maydon BO'SH qoladi — hech narsa taxmin qilinmaydi.
"""
import re
from datetime import date, timedelta

from .numbers import normalize_apostrophes, words_to_numbers

NEG = r"(?:yo'q|kuzatilmadi|aniqlanmadi|kuzatilmaydi|topilmadi|manfiy|yo'qligi|qayd etilmadi)"
MONTHS = {"yanvar": 1, "fevral": 2, "mart": 3, "aprel": 4, "may": 5, "iyun": 6, "iyul": 7, "avgust": 8,
          "sentabr": 9, "sentyabr": 9, "oktabr": 10, "oktyabr": 10, "noyabr": 11, "dekabr": 12}


def prepare(text):
    return words_to_numbers(normalize_apostrophes(text or ""))


def _sentences(text):
    return [s.strip() for s in re.split(r"(?<=[.!?;])\s+|\n+", text) if s.strip()]


def _num(s):
    return float(s.replace(",", "."))


class _Out:
    def __init__(self):
        self.fields, self.evidence = {}, {}

    def set(self, field, value, evidence):
        if value is None or field in self.fields:
            return
        self.fields[field] = value
        self.evidence[field] = evidence.strip()


def _search(pattern, text):
    return re.search(pattern, text, re.IGNORECASE)


def _negated(text, m):
    tail = text[m.end(): m.end() + 25]
    head = text[max(0, m.start() - 12): m.start()]
    return bool(re.match(rf"[\s,:\-]*(?:\w+\s)?{NEG}", tail, re.I) or re.search(r"\b(?:yo'q|siz)\b\s*$", head, re.I))


def _flag(o, field, pattern, text):
    m = _search(pattern, text)
    if m:
        o.set(field, not _negated(text, m), _context(text, m))


def _context(text, m, width=40):
    s = max(0, m.start() - 10)
    e = min(len(text), m.end() + width)
    return text[s:e].split(".")[0] if "." in text[m.start():e] else text[s:e]


def _sentence_with(text, pattern):
    for s in _sentences(text):
        if re.search(pattern, s, re.I):
            return s
    return None


def _strip_lead(sentence, pattern):
    return re.sub(rf"^.*?{pattern}\w*\s*[:\-–]?\s*", "", sentence, count=1, flags=re.I).rstrip(".").strip() or sentence


def _next_visit(text, today):
    m = _search(r"(\d{1,2})\s*(kun|hafta|oy)\w*\s*(?:dan|o'tib)?\s*(?:keyin|so'ng|o'tib)", text)
    if m and _search(r"keyingi|qayta|ko'rik|kelsin|kelish", text[max(0, m.start() - 60): m.end() + 30]):
        n, unit = int(m.group(1)), m.group(2).lower()
        days = n * {"kun": 1, "hafta": 7, "oy": 30}[unit]
        return today + timedelta(days=days), m.group(0)
    m = _search(r"(?:keyingi|qayta)[^.]{0,30}?(\d{1,2})\s*-?\s*(" + "|".join(MONTHS) + r")", text)
    if m:
        day, month = int(m.group(1)), MONTHS[m.group(2).lower()]
        year = today.year + (1 if month < today.month else 0)
        try:
            return date(year, month, day), m.group(0)
        except ValueError:
            return None, None
    return None, None


def _common_tail(o, text, today):
    s = _sentence_with(text, r"shikoyat")
    if s and not re.search(rf"shikoyat\w*\s*{NEG}", s, re.I):
        before, _, after = re.split(r"(shikoyat\w*)", s, maxsplit=1, flags=re.I)
        after = re.sub(r"^\s*(?:qil\w*|bor|:|-)\s*", "", after).rstrip(".").strip()
        if after:
            value = after
        else:  # "Bemor bosh og'rig'iga shikoyat qiladi" → shikoyat oldingi qism
            value = re.sub(r"^(?:bemor|ayol|ona)\s+", "", before.strip(), flags=re.I)
            value = re.sub(r"(?:ga|ka|qa)\s*$", "", value).strip()
        o.set("complaints", value or s, s)
    s = _sentence_with(text, r"tashxis|xulosa")
    if s:
        o.set("diagnosis", _strip_lead(s, r"(?:tashxis|xulosa)"), s)
    s = _sentence_with(text, r"tavsiya")
    if s:
        o.set("recommendation", _strip_lead(s, "tavsiya"), s)
    d, ev = _next_visit(text, today)
    if d:
        o.set("next_visit_date", d.isoformat(), ev)


def extract_mother(raw_text, today=None):
    today = today or date.today()
    text = prepare(raw_text)
    o = _Out()

    m = _search(r"(\d{1,2})\s*-?\s*(?:inchi|nchi|chi)?\s*-?\s*hafta", text)
    if m:
        o.set("gestational_week", int(m.group(1)), m.group(0))
    m = _search(r"(?:qon\s+)?bosim\w*[^.\d]{0,20}?(\d{2,3})\s*(?:ga|/|na|-|dan)\s*(\d{2,3})", text) or \
        _search(r"\b(\d{2,3})\s*(?:ga|/)\s*(\d{2,3})\b", text)
    if m:
        o.set("bp_sys", int(m.group(1)), m.group(0))
        o.set("bp_dia", int(m.group(2)), m.group(0))
    m = _search(r"(?:gemoglobin|hemoglobin|\bhb\b|gemoglabin)\w*[^.\d]{0,20}?(\d{2,3})", text)
    if m:
        o.set("hb", int(m.group(1)), m.group(0))

    m = _search(r"(?:siydik|peshob)\w*[^.]{0,25}?oqsil\w*[^.]{0,30}", text) or _search(r"oqsil\w*[^.]{0,30}", text)
    if m:
        frag = m.group(0)
        if pm := re.search(r"(\d)\s*(?:plyus|plus|\+)", frag, re.I):
            val = "+" * min(int(pm.group(1)), 3)
        elif pm := re.search(r"(\+{1,3})", frag):
            val = pm.group(1)
        elif re.search(r"izlar|iz\b", frag, re.I):
            val = "trace"
        elif re.search(NEG, frag, re.I):
            val = "none"
        else:
            val = "+" if re.search(r"bor|aniqlandi|topildi", frag, re.I) else None
        o.set("urine_protein", val, frag)

    m = _search(r"homila\s+harakat\w*[^.]{0,40}", text)
    if m:
        frag = m.group(0)
        if re.search(r"sust|kamay|kam\b|susay", frag, re.I):
            o.set("fetal_movement", "decreased", frag)
        elif re.search(r"sezilmay|sezmay|yo'q|to'xta", frag, re.I):
            o.set("fetal_movement", "absent", frag)
        elif re.search(r"yaxshi|normal|faol|me'yor|bor|sezil", frag, re.I):
            o.set("fetal_movement", "normal", frag)
    m = _search(r"yurak\s+urish\w*[^.\d]{0,25}?(\d{2,3})", text)
    if m:
        o.set("fetal_heart_rate", int(m.group(1)), m.group(0))
    m = _search(r"vazn\w*[^.\d]{0,15}?(\d{2,3}(?:[.,]\d)?)\s*(?:kg|kilo)?", text)
    if m:
        o.set("weight", _num(m.group(1)), m.group(0))
    m = _search(r"harorat\w*[^.\d]{0,15}?(3\d(?:[.,]\d)?)", text)
    if m:
        o.set("temperature", _num(m.group(1)), m.group(0))

    _flag(o, "edema", r"\bshish\w*", text)
    _flag(o, "bleeding", r"qon\s+ketish\w*|qonli\s+ajralma\w*", text)
    m = _search(r"ko'z\s+oldi\s+qorong'i\w*|ko'rish\w*\s+buzil\w*|kuchli\s+bosh\s+og'ri\w*", text)
    if m:
        o.set("headache_vision", not _negated(text, m), m.group(0))

    s = _sentence_with(text, r"asorat|anamnez|oldingi\s+homiladorlik")
    if s:
        o.set("complications", s.rstrip("."), s)
    _common_tail(o, text, today)
    return o.fields, o.evidence


def extract_child(raw_text, today=None):
    today = today or date.today()
    text = prepare(raw_text)
    o = _Out()

    m = _search(r"vazn\w*[^.\d]{0,15}?(\d)\s*(?:kilo|kg)\w*\s*(\d{1,3})?\s*(?:gramm|gr|g)?", text)
    if m and not _search(r"vazn\w*[^.\d]{0,15}?\d{3,4}\s*(?:gramm|gr|g)\b", text):
        grams = int(m.group(1)) * 1000 + int(m.group(2) or 0)
        o.set("weight", grams, m.group(0))
    m = _search(r"vazn\w*[^.\d]{0,15}?(\d[.,]\d{1,3})\s*(?:kilo|kg)", text)
    if m:
        o.set("weight", int(round(_num(m.group(1)) * 1000)), m.group(0))
    m = _search(r"vazn\w*[^.\d]{0,15}?(\d{3,4})", text)
    if m:
        o.set("weight", int(m.group(1)), m.group(0))
    m = _search(r"bosh\s+aylana\w*[^.\d]{0,15}?(\d{2}(?:[.,]\d)?)", text)
    if m:
        o.set("head_circ", _num(m.group(1)), m.group(0))
    m = _search(r"ko'krak\s+aylana\w*[^.\d]{0,15}?(\d{2}(?:[.,]\d)?)", text)
    if m:
        o.set("chest_circ", _num(m.group(1)), m.group(0))
    m = _search(r"bo'y\w*[^.\d]{0,15}?(\d{2,3})", text)
    if m:
        o.set("height", int(m.group(1)), m.group(0))
    m = _search(r"harorat\w*[^.\d]{0,15}?(3\d(?:[.,]\d)?)", text)
    if m:
        o.set("temperature", _num(m.group(1)), m.group(0))

    m = _search(r"yomon\s+em\w*|emmay\w*|emishdan\s+bosh\s+tort\w*|kam\s+em\w*", text)
    if m:
        o.set("feeding", "poor", m.group(0))
    else:
        m = _search(r"aralash\s+ovqat\w*|aralash", text)
        if m:
            o.set("feeding", "mixed", m.group(0))
        m = _search(r"sun'iy\s+ovqat\w*|smes\w*|aralashma\w*", text)
        if m:
            o.set("feeding", "formula", m.group(0))
        m = _search(r"ko'krak\s+(?:suti|bilan)\w*", text)
        if m:
            o.set("feeding", "breast", m.group(0))

    _flag(o, "jaundice", r"sariqlik\w*|sarg'ay\w*|teri\w*\s+sariq\w*", text)
    _flag(o, "breathing_problem", r"nafas\w*\s+(?:olish\w*\s+)?qiyin\w*|hansira\w*", text)
    _flag(o, "convulsions", r"tutqanoq\w*|talvasa\w*|tirishish\w*", text)
    _common_tail(o, text, today)
    return o.fields, o.evidence
