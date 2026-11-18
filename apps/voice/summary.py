"""AI xulosa: bemorning barcha ko'riklari dinamikasidan shifokorga qisqa tahlil.

Ikki qatlam:
1) facts() — kod bilan hisoblangan aniq faktlar (trendlar, chegaradan chiqishlar, kechikishlar). Har doim ishlaydi.
2) VoiceLab LLM (aisha-orbit) faqat shu faktlar va ko'rik yozuvlari asosida xulosa yozadi; yangi raqam o'ylab topmaydi.
Zona rangini AI emas, rules.json qoidalari belgilaydi — AI faqat tahlil va eslatma beradi.
"""
import json
from datetime import date

from django.conf import settings
from django.core.cache import cache

from apps.risk import norms

from . import voicelab

LANG_NAME = {"uz": "Uzbek (Latin script)", "ru": "Russian", "en": "English"}


def _trend(vals, label, unit, low=None, high=None):
    pts = [(d, v) for d, v in vals if v is not None]
    if len(pts) < 2:
        return None
    (d0, a), (d1, b) = pts[0], pts[-1]
    diff = b - a
    if abs(diff) < 1e-9:
        return None
    s = f"{label}: {a}→{b} {unit} ({d0:%d.%m}→{d1:%d.%m}, {'+' if diff > 0 else ''}{round(diff, 1)})"
    if low is not None and b < low:
        s += " — me'yordan past"
    if high is not None and b > high:
        s += " — me'yordan yuqori"
    return s


def norm_table(visits):
    """Oxirgi ko'rik ko'rsatkichlari me'yor bilan + butun kuzatuvdagi min/max (UI va AI uchun)."""
    if not visits:
        return []
    rows = norms.assess_visit(visits[-1])
    for r in rows:
        if r["field"] in norms.NORMS:
            r["range"] = norms.series_range(visits, r["field"])
    return rows


def facts(p):
    visits = list(p.visits.order_by("visit_date", "created_at"))
    out = []
    for r in norm_table(visits):
        if r["level"]:
            rng = r.get("range")
            extra = f"; kuzatuv davomida min {rng['min']}, max {rng['max']}" if rng and rng["n"] > 1 else ""
            out.append(f"{r['label']}: {r['value']} {r['unit']} — me'yor {r['norm']}, {r['note']}{extra}")
    t = _trend([(v.visit_date, v.hb) for v in visits], "Gemoglobin", "g/l", low=110)
    if t:
        out.append(t)
    t = _trend([(v.visit_date, v.bp_sys) for v in visits], "Sistolik qon bosimi", "mm", high=139)
    if t:
        out.append(t)
    t = _trend([(v.visit_date, float(v.weight) if v.weight else None) for v in visits], "Vazn", "kg")
    if t:
        out.append(t)
    prot = [v for v in visits if v.urine_protein in ("+", "++", "+++")]
    if prot:
        out.append(f"Siydikda oqsil {len(prot)} ko'rikda aniqlangan (oxirgisi {prot[-1].visit_date:%d.%m}: {prot[-1].urine_protein})")
    flags = [v for v in visits if v.edema or v.bleeding or v.headache_vision]
    if flags:
        v = flags[-1]
        sym = [n for n, f in (("shish", v.edema), ("qon ketishi", v.bleeding), ("bosh og'rig'i/ko'rish", v.headache_vision)) if f]
        out.append(f"Xavf belgilari: {', '.join(sym)} ({v.visit_date:%d.%m})")
    if p.missed_visit:
        out.append(f"Keyingi ko'rik sanasi o'tib ketgan: {p.next_visit_date:%d.%m.%Y}")
    if p.chronic_conditions:
        out.append(f"Surunkali kasalliklar: {p.chronic_conditions}")
    if p.previous_complications:
        out.append(f"Oldingi asoratlar: {p.previous_complications}")
    return out, visits


def _payload(p, fs, visits):
    rows = []
    for v in visits[-8:]:
        rows.append({k: val for k, val in {
            "sana": f"{v.visit_date:%Y-%m-%d}", "hafta": v.gestational_week, "QB": v.bp,
            "Hb": v.hb, "oqsil": v.urine_protein or None, "YUU": v.fetal_heart_rate,
            "vazn": float(v.weight) if v.weight else None, "shikoyat": v.complaints or None,
            "xulosa": v.diagnosis or None, "zona": v.final_color}.items() if val not in (None, "")})
    return {
        "yosh": p.age, "homiladorlik_haftasi": p.gestational_weeks, "nechanchi_homiladorlik": p.gravidity,
        "joriy_zona": p.current_color, "zona_sabablari": p.color_reasons, "faktlar": fs, "koriklar": rows,
        "meyorlar": {k: {"min": n["min"], "max": n["max"], "birlik": n["unit"], "manba": n["source"]}
                     for k, n in norms.NORMS.items()},
        "oxirgi_korik_baholash": [{k: r[k] for k in ("label", "value", "unit", "norm", "note")} for r in norm_table(visits)],
        "keyingi_korik": p.next_visit_date.isoformat() if p.next_visit_date else None,
        "bugun": date.today().isoformat(),
    }


SYSTEM = (
    "Sen oilaviy poliklinika shifokoriga yordam beradigan perinatal tahlilchisan. Senga homilador ayolning "
    "ko'riklari va kod hisoblagan faktlar beriladi. Faqat shu ma'lumotga tayan, yangi raqam yoki tashxis o'ylab "
    "topma. Har qiymatni berilgan me'yorlar (min/max) bilan solishtir. O'zbekiston SSV antenatal standarti "
    "(8 tashrif) va JSST tavsiyalariga mos qisqa, amaliy xulosa yoz. "
    "Alohida patient_message maydoniga ONAGA botda yuboriladigan xabar yoz: faqat o'zbek tilida (lotin), sodda, "
    "xotirjam va iliq ohangda, 3-5 gap. Unda zona rangi, tashxis nomlari, qo'rqituvchi so'zlar (xavfli, jiddiy, "
    "preeklampsiya, gipoksiya, o'lim, asorat) BO'LMASIN. Nima qilish kerakligini ayt: keyingi ko'rik sanasi, "
    "shifokor tavsiyalariga amal qilish, ovqatlanish/dam olish; oxirida yumshoq qilib: o'zini yomon his qilsa "
    "(kuchli bosh og'rig'i, qon kelishi, homila harakati kamaysa) poliklinikaga murojaat qilsin. "
    "patient_steps maydoniga onaga 3-5 ta amaliy maslahat yoz (ovqatlanish, dam olish, dori, nazorat) — xuddi shu "
    "qoidalar bilan: tashxis va qo'rqituvchi so'zlarsiz. "
    "Har band 1 qisqa gap bo'lsin. IMPORTANT: write every field of the answer ONLY in {lang}."
)
SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string", "description": "1-2 gaplik umumiy holat"},
        "trends": {"type": "array", "items": {"type": "string"}, "description": "Nima o'zgaryapti (2-4 band)"},
        "attention": {"type": "array", "items": {"type": "string"}, "description": "E'tibor beriladigan xavflar (0-3)"},
        "next_steps": {"type": "array", "items": {"type": "string"}, "description": "Shifokor uchun keyingi qadamlar (2-4)"},
        "patient_message": {"type": "string", "description": "Onaga xotirjam, vahimasiz umumiy xulosa (o'zbekcha, 2-4 gap)"},
        "patient_steps": {"type": "array", "items": {"type": "string"},
                          "description": "Onaga nima qilish kerak: 3-5 ta sodda, xotirjam maslahat (o'zbekcha)"},
    },
    "required": ["summary", "trends", "attention", "next_steps", "patient_message", "patient_steps"],
}


def summarize(p, lang="uz", force=False):
    """Qaytaradi: dict(engine, summary, trends, attention, next_steps, facts, error)."""
    fs, visits = facts(p)
    last = visits[-1].id if visits else 0
    key = f"aisum:{p.id}:{last}:{p.current_color}:{lang}"
    if not force and (hit := cache.get(key)):
        return hit
    res = {"engine": "facts", "summary": "", "trends": fs, "attention": [], "next_steps": [], "facts": fs, "error": None,
           "table": norm_table(visits)}
    res["patient_message"] = full_message(p, res["table"], "", [])
    if settings.VOICE_MODE == "voicelab" and visits:
        try:
            ai = voicelab.chat_tool(SYSTEM.format(lang=LANG_NAME.get(lang, LANG_NAME["uz"])),
                                    json.dumps(_payload(p, fs, visits), ensure_ascii=False)
                                    + f"\n\nAnswer language: {LANG_NAME.get(lang, LANG_NAME['uz'])}.",
                                    "patient_summary", "Bemor bo'yicha shifokorga xulosa", SCHEMA, timeout=45)
            res.update({k: ai.get(k) or ([] if k != "summary" else "") for k in ("summary", "trends", "attention", "next_steps")})
            res["patient_message"] = full_message(p, res["table"], (ai.get("patient_message") or "").strip(),
                                                  [x for x in (ai.get("patient_steps") or []) if str(x).strip()])
            res["engine"] = "voicelab-llm"
        except voicelab.VoiceLabError as e:
            res["error"] = str(e)
    res["patient_flags"] = alarming_words(res["patient_message"])
    cache.set(key, res, 3600)
    return res


# Onaga boradigan matnda bo'lmasligi kerak bo'lgan so'zlar — shifokor yuborishdan oldin ogohlantiriladi
ALARM = ["qizil", "sariq", "zona", "xavfli", "jiddiy", "preeklampsi", "eklampsi", "gipoksi", "o'lim", "asorat",
         "patologi", "kritik", "shoshilinch", "tez yordam", "operatsiya", "tashxis", "anemiya", "gipertenziya"]


def alarming_words(text):
    t = (text or "").lower().replace("ʻ", "'").replace("‘", "'").replace("’", "'")
    return [w for w in ALARM if w in t]


STATUS_WORD = {0: "me'yorda ✅", 1: "me'yordan farq qiladi — shifokoringiz kuzatadi", 2: "me'yordan farq qiladi — shifokoringiz kuzatadi"}
MOTHER_LABEL = {"bp_sys": None, "bp_dia": None}  # qon bosimi bitta qatorda


def _norm_lines(table):
    rows = {r["field"]: r for r in table}
    out = []
    if "bp_sys" in rows and "bp_dia" in rows:
        lvl = max(rows["bp_sys"]["level"], rows["bp_dia"]["level"])
        out.append(f"• Qon bosimi: {rows['bp_sys']['value']}/{rows['bp_dia']['value']} (me'yor 90–139 / 60–89) — {STATUS_WORD[lvl]}")
    for f, r in rows.items():
        if f in ("bp_sys", "bp_dia"):
            continue
        unit = f" {r['unit']}" if r["unit"] and r["unit"] != "1 daq." else ""
        out.append(f"• {r['label']}: {r['value']}{unit} (me'yor {r['norm']}) — {STATUS_WORD[r['level']]}")
    return out


DEFAULT_STEPS = ["Shifokor tavsiya qilgan dorilarni to'liq va o'z vaqtida iching",
                 "Temirga boy ovqatlar yeng: go'sht, jigar, dukkaklilar, ko'katlar; ko'proq suv iching",
                 "Yetarlicha uxlang va dam oling, og'ir yuk ko'tarmang",
                 "Ko'rikka belgilangan kunda keling"]
WARNING_SIGNS = ("Agar quyidagilar bo'lsa, kutmasdan poliklinikaga yoki 103 ga murojaat qiling: qon kelishi, kuchli "
                 "bosh og'rig'i yoki ko'z oldi qorong'ilashishi, homila harakati kamayishi, suv ketishi, yuqori harorat. "
                 "Botdagi «🚨 Xavf belgilari» tugmasi orqali ham xabar berishingiz mumkin.")


def full_message(p, table, summary_text, steps):
    """Onaga to'liq, xotirjam xulosa: umumiy holat + ko'rsatkichlar me'yor bilan + maslahatlar + xavf belgilari + sana."""
    parts = [f"Hurmatli {p.first_name}, ko'rik natijalaringiz shifokoringiz tomonidan ko'rib chiqildi."]
    if summary_text:
        parts = [summary_text]
    lines = _norm_lines(table)
    if lines:
        parts.append("📊 Ko'rsatkichlaringiz:\n" + "\n".join(lines))
    parts.append("✅ Nima qilish kerak:\n" + "\n".join(f"• {x}" for x in (steps or DEFAULT_STEPS)[:5]))
    if p.next_visit_date:
        parts.append(f"📅 Keyingi ko'rigingiz: {p.next_visit_date:%d.%m.%Y}")
    parts.append("⚠️ " + WARNING_SIGNS)
    return "\n\n".join(parts)


def fallback_message(p):
    """AI ishlamasa: shablon asosidagi xotirjam xabar."""
    parts = [f"Hurmatli {p.first_name}, ko'rik natijalaringiz shifokoringiz tomonidan ko'rib chiqildi."]
    if p.next_visit_date:
        parts.append(f"Keyingi ko'rigingiz: {p.next_visit_date:%d.%m.%Y}. Iltimos, o'z vaqtida keling.")
    parts.append("Shifokor tavsiyalariga amal qiling, to'g'ri ovqatlaning va yetarlicha dam oling.")
    parts.append("Agar o'zingizni yomon his qilsangiz — kuchli bosh og'rig'i, qon kelishi yoki homila harakati "
                 "kamaysa — poliklinikaga murojaat qiling.")
    return " ".join(parts)
