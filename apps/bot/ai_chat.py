"""Onalar uchun AI yordamchi (botda): ona oddiy savol yozadi — VoiceLab aisha-orbit javob beradi.

Xavfsizlik: tashxis qo'ymaydi, dori dozasi aytmaydi, zona rangini aytmaydi; xavf belgisi yozilsa —
AI javobidan oldin shifokorga QIZIL signal ketadi va onaga 103 / «Xavf belgilari» eslatiladi.
Har savol-javob saytda «Telegram xabarlar» logida (turi: AI yordamchi) ko'rinadi.
"""
import html
import re
from collections import defaultdict, deque
from datetime import date

from django.conf import settings

from apps.alerts.models import Notification
from apps.voice import voicelab

HISTORY = defaultdict(lambda: deque(maxlen=6))  # chat_id → oxirgi savol-javoblar (xotirada)

# Shoshilinch belgilar (o'zbek lotin/kirill va rus) — LLM'ga tayanmasdan darhol signal
DANGER = [r"qon\s*ket", r"qon\s*kel", r"tutqanoq", r"tirish", r"hush(i|dan)\s*ket", r"suv(i)?\s*ket",
          r"qimirla(ma|y)\w*\s*(yo'q|qoldi)|qimirlamay", r"harakat\w*\s*(yo'q|kamay|sezilmay)", r"emma(y|ya)",
          r"nafas\w*\s*(qiyin|ololmay|yetishmay)", r"ko'?z\s*oldi\s*qorong'?i", r"kuchli\s*bosh\s*og'?ri",
          r"кровотеч", r"судорог", r"не\s*шевел", r"воды\s*отош", r"потер\w*\s*сознан", r"не\s*сосет"]
DANGER_RE = re.compile("|".join(DANGER), re.IGNORECASE)

SYSTEM = (
    "Sen «Perinatal registr» Telegram botidagi homilador ayollar va yosh onalar uchun yordamchisan. "
    "Faqat o'zbek tilida (lotin), sodda, iliq va xotirjam javob ber, 3-7 gap. "
    "Homiladorlik, tug'ruqdan keyingi davr, emizish, chaqaloq parvarishi, ovqatlanish, emlash va ko'riklar "
    "haqida umumiy, JSST va O'zbekiston SSV tavsiyalariga mos ma'lumot ber. QOIDALAR: "
    "1) Tashxis qo'yma va dori nomi yoki dozasini tavsiya qilma — «shifokoringiz belgilaydi» de. "
    "2) Zona, xavf darajasi, «qizil/sariq» kabi so'zlarni ishlatma, vahima qilma. "
    "3) Onaning ma'lumotlari (quyida) kerak bo'lsa ishlat: keyingi ko'rik sanasi, homiladorlik haftasi, "
    "farzandining emlashi. Ma'lumot bo'lmasa, o'ylab topma. "
    "4) Xavfli belgilar (qon ketishi, tutqanoq, kuchli bosh og'rig'i, homila harakati kamayishi, suv ketishi, "
    "chaqaloq emmasligi yoki nafas qiyinligi) haqida so'rasa — darhol 103 ga qo'ng'iroq qilish yoki botdagi "
    "«🚨 Xavf belgilari» tugmasini bosishni ayt. "
    "5) Mavzudan tashqari savollarga (siyosat, dasturlash va h.k.) muloyimlik bilan javob berma. "
    "6) Oxirida qisqa qilib: aniq maslahat uchun oilaviy poliklinikangizga murojaat qiling."
)


def context(p):
    lines = [f"Ism: {p.first_name}, yoshi: {p.age}", f"Holat: {p.get_status_display()}"]
    if p.status == "pregnant" and p.gestational_weeks:
        lines.append(f"Homiladorlik muddati: {p.gestational_weeks} hafta; kutilayotgan tug'ruq: {p.edd:%d.%m.%Y}")
    if p.next_visit_date:
        lines.append(f"Keyingi ko'rik: {p.next_visit_date:%d.%m.%Y}")
    lines.append(f"Poliklinika: {p.mavze.clinic.name}")
    v = p.visits.order_by("-visit_date", "-created_at").first()
    if v:
        vals = [x for x in (f"qon bosimi {v.bp}" if v.bp else "", f"gemoglobin {v.hb} g/l" if v.hb else "",
                            f"vazn {v.weight} kg" if v.weight else "") if x]
        lines.append(f"Oxirgi ko'rik {v.visit_date:%d.%m.%Y}: " + ", ".join(vals))
        if v.recommendation:
            lines.append(f"Shifokor tavsiyasi: {v.recommendation}")
    for c in p.children.filter(birth_date__gte=date.today().replace(year=date.today().year - 2)):
        nxt = c.vaccinations.exclude(status="done").select_related("vaccine").order_by("due_date").first()
        s = f"Farzandi: {c.first_name}, {c.age_label}"
        if nxt:
            s += f"; navbatdagi emlash: {nxt.vaccine.name} ({nxt.due_date:%d.%m.%Y})"
        if c.next_visit_date:
            s += f"; keyingi ko'rik: {c.next_visit_date:%d.%m.%Y}"
        lines.append(s)
    return "\n".join(lines)


def is_danger(text):
    return bool(DANGER_RE.search(text or ""))


def answer(p, chat_id, question):
    """Qaytaradi: (javob_matni_html, xavf_signal_yuborildimi)."""
    question = question.strip()[:800]
    alerted = False
    if is_danger(question):
        from apps.alerts import danger
        danger.report(p, "other", None, question)
        alerted = True
    if settings.VOICE_MODE != "voicelab":
        reply = "AI yordamchi hozir ishlamayapti. Savolingiz bo'yicha oilaviy poliklinikangizga murojaat qiling."
    else:
        msgs = [{"role": "system", "content": SYSTEM + "\n\nONA HAQIDA MA'LUMOT:\n" + context(p)}]
        msgs += list(HISTORY[chat_id]) + [{"role": "user", "content": question}]
        try:
            reply = voicelab.chat(msgs)
        except voicelab.VoiceLabError:
            reply = ""
        if not reply:
            reply = "Kechirasiz, hozir javob bera olmadim. Birozdan keyin qayta yozing yoki poliklinikangizga murojaat qiling."
        else:
            HISTORY[chat_id].extend([{"role": "user", "content": question}, {"role": "assistant", "content": reply}])
    reply = re.sub(r"\*\*(.+?)\*\*", r"\1", reply)[:1800]  # markdown qalin belgilarini olib tashlash
    body = html.escape(reply, quote=False)
    if alerted:
        body = ("🚨 <b>Shifokoringizga darhol xabar yuborildi.</b> Ahvol og'ir bo'lsa — kutmang, <b>103</b> ga "
                "qo'ng'iroq qiling.\n\n") + body
    Notification.objects.create(recipient_label=f"{p.short_name} (ona) · AI", chat_id=chat_id, kind="ai_chat",
                                text=f"❓ {question}\n\n🤖 {reply}", status=Notification.SENT, patient=p)
    return "🤖 " + body, alerted
