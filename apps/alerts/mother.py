"""Onaga botda boradigan xabarlar: ko'rik natijalari, ko'rilgan chora, yo'llanma.

Qoida: onaga zona rangi ("qizil", "sariq") aytilmaydi — faqat shifokor kiritgan ma'lumot va yozgan matn.
Har xabar ostida "✅ Tasdiqlayman / ❌ Bunday bo'lmadi" tugmalari — shifokor qilinmagan ishni
"qildim" deb yozsa yoki o'tkazilmagan ko'rikni kiritsa, ona buni rad etadi va yuqori bosqich darhol biladi.
"""
import html

from django.utils import timezone

from apps.bot import sender

from .models import MotherConfirmation, Notification


def esc(s):
    return html.escape(str(s), quote=False)


def _d(d):
    return d.strftime("%d.%m.%Y") if d else "—"


def _send(patient, kind, obj_id, author, summary, body):
    mc = MotherConfirmation.objects.create(kind=kind, object_id=obj_id, patient=patient, author=author,
                                           summary=summary[:255])
    body += "\n\n<i>Ma'lumot to'g'rimi? Javobingiz shifokor ishini nazorat qilishga yordam beradi.</i>"
    buttons = [[("✅ Tasdiqlayman", f"mc:{mc.id}:y"), ("❌ Bunday bo'lmadi", f"mc:{mc.id}:n")]]
    n = sender.send(patient.telegram_chat_id, body, kind="confirm", recipient_label=f"{patient.short_name} (ona)",
                    buttons=buttons, patient=patient)
    mc.delivered = n.status == Notification.SENT
    mc.save(update_fields=["delivered"])
    return mc


def _doctor_line(user, clinic):
    who = esc(user.full_name or user.username) if user else "—"
    return f"👩‍⚕️ {who}, {esc(clinic.name)}"


def visit(v):
    """Ona ko'rigi saqlangach."""
    p = v.patient
    lines = [f"🩺 <b>Ko'rik natijalari — {_d(v.visit_date)}</b>", _doctor_line(v.doctor, p.clinic)]
    if v.gestational_week:
        lines.append(f"Homiladorlik muddati: {v.gestational_week} hafta")
    vals = []
    if v.bp:
        vals.append(f"qon bosimi {v.bp}")
    if v.hb:
        vals.append(f"gemoglobin {v.hb} g/l")
    if v.urine_protein:
        vals.append(f"siydikda oqsil: {v.get_urine_protein_display().lower()}")
    if v.fetal_heart_rate:
        vals.append(f"homila yurak urishi {v.fetal_heart_rate}")
    if v.weight:
        vals.append(f"vazn {v.weight} kg")
    if vals:
        lines.append("O'lchovlar: " + ", ".join(vals))
    if v.complaints:
        lines.append(f"Shikoyat: {esc(v.complaints)}")
    if v.diagnosis:
        lines.append(f"Xulosa: {esc(v.diagnosis)}")
    if v.recommendation:
        lines.append(f"Tavsiya: {esc(v.recommendation)}")
    if v.next_visit_date:
        lines.append(f"\n📅 Keyingi ko'rik: <b>{_d(v.next_visit_date)}</b>")
    return _send(p, MotherConfirmation.VISIT, v.id, v.doctor, f"Ko'rik {_d(v.visit_date)}", "\n".join(lines))


def child_visit(v):
    c = v.child
    lines = [f"👶 <b>{esc(c.first_name)} — ko'rik natijalari ({_d(v.visit_date)})</b>", _doctor_line(v.doctor, c.mother.clinic)]
    vals = []
    if v.weight:
        vals.append(f"vazn {v.weight} g")
    if v.height:
        vals.append(f"bo'y {v.height} sm")
    if v.head_circ:
        vals.append(f"bosh aylanasi {v.head_circ} sm")
    if v.temperature:
        vals.append(f"harorat {v.temperature}°C")
    if vals:
        lines.append("O'lchovlar: " + ", ".join(vals))
    if v.specialists:
        lines.append("Mutaxassislar: " + esc("; ".join(v.specialists)))
    if v.diagnosis:
        lines.append(f"Xulosa: {esc(v.diagnosis)}")
    if v.recommendation:
        lines.append(f"Tavsiya: {esc(v.recommendation)}")
    if v.next_visit_date:
        lines.append(f"\n📅 Keyingi ko'rik: <b>{_d(v.next_visit_date)}</b>")
    return _send(c.mother, MotherConfirmation.CHILD_VISIT, v.id, v.doctor,
                 f"{c.first_name}: ko'rik {_d(v.visit_date)}", "\n".join(lines))


ACTION_TEXT = {  # onaga tushunarli shakl
    "call": "Shifokor holatingiz bo'yicha bog'landi",
    "consult": "Siz qo'shimcha konsultatsiyaga chaqirildingiz",
    "hospital": "Sizni statsionarga yotqizish belgilandi",
    "order": "Sizga perinatal markazga order (yo'llanma) berildi",
    "observe": "Siz qo'shimcha nazoratga olindingiz",
    "other": "Shifokor chora ko'rdi",
}


def action(alert):
    """Signal bo'yicha chora ko'rilgach — shifokor nima yozgan bo'lsa, shu onaga boradi."""
    p = alert.patient
    who = alert.resolved_by
    subject = f"farzandingiz {esc(alert.child.first_name)}" if alert.child_id else "siz"
    lines = [f"📌 <b>Shifokor qarori — {_d(timezone.localdate(alert.resolved_at))}</b>",
             f"👩‍⚕️ {esc(who.full_name or who.username) if who else '—'} ({esc(who.get_role_display()) if who else ''})",
             f"{ACTION_TEXT.get(alert.action_type, ACTION_TEXT['other'])}" + (f" ({subject})" if alert.child_id else "") + "."]
    if alert.action_note:
        lines.append(f"Izoh: {esc(alert.action_note)}")
    return _send(p, MotherConfirmation.ALERT, alert.id, who, ACTION_TEXT.get(alert.action_type, "Chora"), "\n".join(lines))


def referral(ref, event):
    """event: issued | acted."""
    p = ref.patient
    whom = "perinatal markazga (order)" if ref.to_level == "ovabmu" else "tuman mutaxassisiga"
    if event == "issued":
        title, text = "📄 <b>Sizga yo'llanma berildi</b>", f"Yo'nalish: {whom}."
        author = ref.from_user
    else:
        title, text = "✅ <b>Yo'llanma bo'yicha qabul qilindingiz</b>", f"Yo'nalish: {whom}."
        author = ref.accepted_by
    lines = [title, f"👩‍⚕️ {esc(author.full_name or author.username) if author else '—'}", text]
    if event == "issued" and ref.reason:
        lines.append(f"Sabab: {esc(ref.reason)}")
    if event == "acted" and ref.action_note:
        lines.append(f"Natija: {esc(ref.action_note)}")
    return _send(p, MotherConfirmation.REFERRAL, ref.id, author, f"Yo'llanma: {event}", "\n".join(lines))


def handle_response(mc, confirmed):
    """Bot callback: ona javob berdi. Rad etsa — saytda belgilanadi va Signallar sahifasida ko'rinadi."""
    if mc.confirmed is not None:
        return False
    mc.confirmed, mc.responded_at = confirmed, timezone.now()
    mc.save(update_fields=["confirmed", "responded_at"])
    # Rad etilgan yozuv saytda "Ona rad etdi" belgisi bilan ko'rinadi (Signallar, bemor kartasi)
    return True


def attach(objs, kind):
    """Har bir obyektga .mc (onaning eng so'nggi javobi) biriktiradi — shablonda ko'rsatish uchun."""
    objs = list(objs)
    ids = [o.id for o in objs]
    latest = {}
    for mc in MotherConfirmation.objects.filter(kind=kind, object_id__in=ids).order_by("created_at"):
        latest[mc.object_id] = mc
    for o in objs:
        o.mc = latest.get(o.id)
    return objs


def stats(kind, object_ids):
    qs = MotherConfirmation.objects.filter(kind=kind, object_id__in=list(object_ids))
    total = qs.count()
    yes = qs.filter(confirmed=True).count()
    no = qs.filter(confirmed=False).count()
    return {"sent": total, "yes": yes, "no": no, "wait": total - yes - no}
