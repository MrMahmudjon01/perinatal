"""O'zbekcha son so'zlarini raqamga aylantirish: 'bir yuz oltmish besh' → 165, 'o'ttiz yetti butun besh' → 37.5."""
import re

APOS = "'‘’ʻʼ`´"
_APOS_RE = re.compile(f"[{re.escape(APOS)}]")

UNITS = {
    "nol": 0, "bir": 1, "ikki": 2, "uch": 3, "to'rt": 4, "tort": 4, "besh": 5, "olti": 6, "yetti": 7,
    "sakkiz": 8, "to'qqiz": 9, "toqqiz": 9,
    "o'n": 10, "on": 10, "yigirma": 20, "o'ttiz": 30, "ottiz": 30, "qirq": 40, "ellik": 50,
    "oltmish": 60, "yetmish": 70, "sakson": 80, "to'qson": 90, "toqson": 90,
}
HUNDRED, THOUSAND = "yuz", "ming"
SUFFIXES = ["inchi", "nchi", "dan", "ga", "da", "ta", "ni", "lik", "ka"]


def normalize_apostrophes(text):
    return _APOS_RE.sub("'", text)


def _split_suffix(word):
    """'oltmishga' → ('oltmish', 'ga'); 'o'ttiz' → ('o'ttiz', '')."""
    w = word.lower()
    if w in UNITS or w in (HUNDRED, THOUSAND):
        return w, ""
    for s in SUFFIXES:
        if w.endswith(s):
            base = w[: -len(s)]
            if base in UNITS or base in (HUNDRED, THOUSAND):
                return base, s
            # 'uchinchi' → 'uch' + 'inchi', 'ikkinchi' → 'ikki' + 'nchi'
            if s in ("nchi", "inchi") and base + "i" in UNITS:
                return base + "i", s
    return None, None


def _value(words):
    total, current = 0, 0
    for w in words:
        if w == HUNDRED:
            current = (current or 1) * 100
        elif w == THOUSAND:
            total += (current or 1) * 1000
            current = 0
        else:
            current += UNITS[w]
    return total + current


def _fmt(v):
    return str(int(v)) if float(v).is_integer() else str(v)


def words_to_numbers(text):
    text = normalize_apostrophes(text)
    tokens = re.findall(r"[\w']+|[^\w'\s]+|\s+", text)
    out, i = [], 0
    while i < len(tokens):
        base, suf = _split_suffix(tokens[i]) if re.match(r"[\w']+$", tokens[i]) else (None, None)
        if base is None:
            out.append(tokens[i])
            i += 1
            continue
        nums, j, suffix = [base], i + 1, suf
        while not suffix:
            # bo'sh joydan keyingi so'z ham son bo'lsa davom etamiz
            if j + 1 < len(tokens) and tokens[j].isspace():
                b, s = _split_suffix(tokens[j + 1]) if re.match(r"[\w']+$", tokens[j + 1]) else (None, None)
                if b is not None:
                    nums.append(b)
                    suffix = s
                    j += 2
                    continue
            break
        value = _value(nums)
        # kasr qism: 'o'ttiz yetti butun besh' / 'o'ttiz yetti yarim'
        if not suffix and j + 1 < len(tokens) and tokens[j].isspace():
            nxt = tokens[j + 1].lower()
            if nxt == "yarim":
                value += 0.5
                j += 2
            elif nxt == "butun" and j + 3 < len(tokens):
                b, s = _split_suffix(tokens[j + 3])
                if b is not None and UNITS.get(b, 99) < 10:
                    value = float(f"{value}.{UNITS[b]}")
                    suffix = s or ""
                    j += 4
        out.append(_fmt(value) + (suffix or ""))
        i = j
    return "".join(out)
