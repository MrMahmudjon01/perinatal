"""Ovozli ko'rik oqimi: audio → matn → maydonlar → tekshiruv."""
from datetime import date

from django.conf import settings

from . import extractor, mock, validate, voicelab

MOTHER_SCHEMA_FIELDS = {
    "gestational_week": {"type": ["integer", "null"], "description": "Homiladorlik haftasi"},
    "bp_sys": {"type": ["integer", "null"], "description": "Sistolik qon bosimi, mm sim. ust."},
    "bp_dia": {"type": ["integer", "null"], "description": "Diastolik qon bosimi"},
    "hb": {"type": ["integer", "null"], "description": "Gemoglobin, g/l"},
    "urine_protein": {"type": ["string", "null"], "enum": ["none", "trace", "+", "++", "+++", None]},
    "fetal_movement": {"type": ["string", "null"], "enum": ["normal", "decreased", "absent", "na", None]},
    "fetal_heart_rate": {"type": ["integer", "null"], "description": "Homila yurak urishi, 1 daqiqada"},
    "weight": {"type": ["number", "null"], "description": "Onaning vazni, kg"},
    "temperature": {"type": ["number", "null"]},
    "edema": {"type": ["boolean", "null"]},
    "bleeding": {"type": ["boolean", "null"]},
    "headache_vision": {"type": ["boolean", "null"], "description": "Kuchli bosh og'rig'i yoki ko'rish buzilishi"},
    "complaints": {"type": ["string", "null"]},
    "complications": {"type": ["string", "null"], "description": "Oldingi asoratlar, anamnez"},
    "diagnosis": {"type": ["string", "null"], "description": "Shifokor aytgan xulosa/tashxis"},
    "recommendation": {"type": ["string", "null"]},
    "next_visit_date": {"type": ["string", "null"], "description": "Keyingi ko'rik sanasi YYYY-MM-DD"},
}
CHILD_SCHEMA_FIELDS = {
    "weight": {"type": ["integer", "null"], "description": "Bola vazni, gramm"},
    "height": {"type": ["integer", "null"], "description": "Bo'yi, sm"},
    "head_circ": {"type": ["number", "null"], "description": "Bosh aylanasi, sm"},
    "chest_circ": {"type": ["number", "null"], "description": "Ko'krak aylanasi, sm"},
    "temperature": {"type": ["number", "null"]},
    "feeding": {"type": ["string", "null"], "enum": ["breast", "mixed", "formula", "poor", None]},
    "jaundice": {"type": ["boolean", "null"]},
    "breathing_problem": {"type": ["boolean", "null"]},
    "convulsions": {"type": ["boolean", "null"]},
    "complaints": {"type": ["string", "null"]},
    "diagnosis": {"type": ["string", "null"]},
    "recommendation": {"type": ["string", "null"]},
    "next_visit_date": {"type": ["string", "null"], "description": "YYYY-MM-DD"},
}

SYSTEM_PROMPT = (
    "Sen tibbiy hujjat yordamchisisan. Shifokor ko'rik paytida aytgan o'zbekcha matndan faqat aniq AYTILGAN "
    "qiymatlarni ajratib olasan. Qoidalar: 1) Aytilmagan maydon uchun null qaytar — hech qachon taxmin qilma. "
    "2) So'z bilan aytilgan sonlarni raqamga aylantir. 3) Har bir to'ldirilgan maydon uchun evidence ichida "
    "matndagi aynan iborani ber. 4) Tashxis qo'yma, faqat shifokor aytganini yoz. Bugungi sana: {today}."
)


def _llm_extract(kind, text):
    props = MOTHER_SCHEMA_FIELDS if kind == "mother" else CHILD_SCHEMA_FIELDS
    schema = {
        "type": "object",
        "properties": {
            "fields": {"type": "object", "properties": props},
            "evidence": {"type": "object", "description": "maydon nomi → matndagi ibora",
                         "additionalProperties": {"type": "string"}},
        },
        "required": ["fields", "evidence"],
    }
    res = voicelab.chat_tool(SYSTEM_PROMPT.format(today=date.today().isoformat()), text,
                             "fill_visit_form", "Ko'rik shablonini to'ldirish", schema)
    return res.get("fields") or {}, res.get("evidence") or {}


def transcribe(audio_file, kind, scenario=None):
    """Qaytaradi: (matn, ogohlantirish yoki None)."""
    if settings.VOICE_MODE != "voicelab":
        return mock.transcript(kind, scenario), None
    data = audio_file.read()
    if len(data) < 2000:
        raise voicelab.VoiceLabError("Audio juda qisqa")
    text, _ = voicelab.transcribe(data, filename=audio_file.name or "audio.webm",
                                  content_type=(audio_file.content_type or "audio/webm").split(";")[0])
    return text, None


def extract(kind, text, lang="uz"):
    """Matndan maydonlar. Qaytaradi: dict(fields, evidence, warnings, engine, notes)."""
    rule_fn = extractor.extract_mother if kind == "mother" else extractor.extract_child
    rule_fields, rule_ev = rule_fn(text)
    notes, engine = [], "rules"
    fields, evidence = dict(rule_fields), dict(rule_ev)
    if settings.VOICE_MODE == "voicelab":
        try:
            llm_fields, llm_ev = _llm_extract(kind, text)
            engine = "voicelab-llm"
            llm_fields = {k: v for k, v in llm_fields.items() if v not in (None, "")}
            fields = {**rule_fields, **llm_fields}  # LLM ustuvor, qoidalar bo'sh joyni to'ldiradi
            evidence = {**rule_ev, **{k: v for k, v in llm_ev.items() if k in llm_fields}}
        except voicelab.VoiceLabError as e:
            notes.append(f"LLM ishlamadi ({e}), qoidaga asoslangan ajratuvchi ishlatildi")
    cleaned, warnings = validate.clean(kind, fields, lang)
    return {"fields": cleaned, "evidence": {k: v for k, v in evidence.items() if k in cleaned},
            "warnings": warnings, "engine": engine, "notes": notes}
