"""Onaning o'zi botda xabar beradigan xavf belgilari (JSST antenatal / IMNCI xavf belgilari asosida).

Ona belgini tanlaydi → saytda darhol QIZIL signal paydo bo'ladi: oilaviy shifokor (o'z poliklinikasi), tuman va
OvaBMU ko'radi; ochiq sahifada toast + ovozli signal. Zona avtomatik o'zgartirilmaydi — shifokor tekshirib qaror qiladi.
"""
from datetime import timedelta

from django.utils import timezone

from .models import Alert

MOTHER_SIGNS = [
    ("bleed", "🩸 Qon ketishi"),
    ("head", "🤕 Kuchli bosh og'rig'i / ko'z oldi qorong'ilashishi"),
    ("move", "🤰 Homila harakati kamaydi"),
    ("water", "💧 Suv ketdi"),
    ("pain", "😣 Qorinda kuchli og'riq"),
    ("fever", "🌡 Yuqori harorat"),
    ("fits", "⚡ Tutqanoq / hushdan ketish"),
    ("other", "📝 Boshqa (o'zim yozaman)"),
]
CHILD_SIGNS = [
    ("feed", "🍼 Emmayapti / ovqat yemayapti"),
    ("fever", "🌡 Isitma"),
    ("breath", "😮‍💨 Nafas olishi qiyin"),
    ("fits", "⚡ Tirishish"),
    ("yellow", "🟡 Sariqlik kuchaydi"),
    ("weak", "😴 Juda holsiz, uyg'onmayapti"),
    ("other", "📝 Boshqa (o'zim yozaman)"),
]
PREGNANT_ONLY = {"move", "water"}


def mother_signs(patient):
    return [(k, l) for k, l in MOTHER_SIGNS if patient.status == "pregnant" or k not in PREGNANT_ONLY]


def label(code, child=False):
    return dict(CHILD_SIGNS if child else MOTHER_SIGNS).get(code)


def report(patient, code, child=None, note=""):
    """Signal yaratadi. Qaytaradi: (alert, yangi_mi). 30 daqiqa ichida bir xil belgi takrorlanmaydi.
    code="other" bo'lsa — onaning o'z so'zlari (note) yoziladi."""
    text = label(code, child is not None)
    if not text:
        return None, False
    name = text.split(" ", 1)[1]
    if code == "other":
        note = " ".join((note or "").split())[:200]
        if not note:
            return None, False
        name = f"«{note}»"
    reason = f"Ona botda xabar berdi: {name}" if child is None else f"Ona botda xabar berdi ({child.first_name}): {name}"
    recent = Alert.objects.filter(patient=patient, child=child, created_at__gte=timezone.now() - timedelta(minutes=30),
                                  reasons__contains=[reason]).first()
    if recent:
        return recent, False
    subj_color = (child.current_color if child else patient.current_color) or "green"
    clinic = patient.mavze.clinic
    a = Alert.objects.create(patient=patient, child=child, clinic=clinic, district=clinic.district,
                             from_color=subj_color, to_color="red", reasons=[reason],
                             changes="📱 Ona o'zi xabar berdi (xavf belgisi)", level=Alert.OVABMU)
    return a, True
