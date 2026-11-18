"""Ko'rik saqlanganda zona yangilash, signal yaratish va yuborish."""
import html

from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.bot import sender
from apps.risk.engine import COLOR_EMOJI, COLOR_LABEL, RED, YELLOW, worse

from .models import Alert, Notification


def esc(s):
    return html.escape(str(s), quote=False)


def _recipients(alert):
    if alert.level == Alert.OVABMU:
        users = list(User.objects.filter(role=User.OVABMU, is_active=True))
        # qizil signal tuman shifokoriga ham ma'lum bo'lishi kerak
        users += list(User.objects.filter(role=User.DISTRICT, district=alert.district, is_active=True))
    else:
        users = list(User.objects.filter(role=User.DISTRICT, district=alert.district, is_active=True))
    return users


def _alert_text(alert, prefix=""):
    e = esc
    lines = [
        f"{prefix}{COLOR_EMOJI[alert.to_color]} <b>{COLOR_LABEL[alert.to_color].upper()} ZONA</b> — {alert.subject_kind.lower()}",
        f"<b>{e(alert.subject_name)}</b>",
        f"🏥 {e(alert.clinic.name)}, {e(alert.district.name)} tumani",
        f"Zona: {COLOR_LABEL[alert.from_color]} → <b>{COLOR_LABEL[alert.to_color]}</b>",
    ]
    if alert.changes:
        lines.append(f"📈 {e(alert.changes)}")
    if alert.reasons:
        lines.append("Sabablar:")
        lines += [f" • {e(r)}" for r in alert.reasons]
    return "\n".join(lines)


def notify_alert(alert, prefix="", kind="alert"):
    """Shifokor va OvaBMU signallarni saytda oladi (jonli panel + toast + ovoz) — Telegram ishlatilmaydi."""
    return None


def _create_alert(*, patient=None, child=None, old, new, reasons, changes):
    mavze = (child.mother if child else patient).mavze
    alert = Alert.objects.create(
        patient=patient if patient else child.mother, child=child,
        district=mavze.clinic.district, clinic=mavze.clinic,
        from_color=old, to_color=new, reasons=reasons, changes=changes,
        level=Alert.OVABMU if new == RED else Alert.DISTRICT,
    )
    return alert


def _diff_mother(prev, visit):
    """Avvalgi ko'rikka nisbatan nima o'zgarganini qisqa matn qiladi: 'Hb 95→68, QB 130/85→165/110'."""
    if not prev:
        return ""
    out = []
    if prev.hb and visit.hb and prev.hb != visit.hb:
        out.append(f"Hb {prev.hb}→{visit.hb}")
    if prev.bp and visit.bp and prev.bp != visit.bp:
        out.append(f"QB {prev.bp}→{visit.bp}")
    if (prev.urine_protein or "none") != (visit.urine_protein or "none") and visit.urine_protein:
        out.append(f"oqsil {prev.get_urine_protein_display() or 'yo`q'}→{visit.get_urine_protein_display()}")
    days = (visit.visit_date - prev.visit_date).days
    if out and days > 0:
        out.append(f"{days} kunda")
    return ", ".join(out)


def apply_mother_visit(visit):
    """Ko'rik tasdiqlangandan keyin chaqiriladi: bemor zonasini yangilaydi, kerak bo'lsa signal yaratadi."""
    patient = visit.patient
    old = patient.current_color
    prev = patient.visits.exclude(pk=visit.pk).order_by("-visit_date", "-created_at").first()
    patient.current_color = visit.final_color
    patient.color_reasons = visit.color_reasons
    patient.color_updated_at = timezone.now()
    if visit.next_visit_date:
        patient.next_visit_date = visit.next_visit_date
    patient.save(update_fields=["current_color", "color_reasons", "color_updated_at", "next_visit_date"])
    if worse(old, visit.final_color):
        return _create_alert(patient=patient, old=old, new=visit.final_color, reasons=visit.color_reasons,
                             changes=_diff_mother(prev, visit))
    return None


def apply_child_visit(visit):
    child = visit.child
    old = child.current_color
    child.current_color = visit.final_color
    child.color_reasons = visit.color_reasons
    child.color_updated_at = timezone.now()
    if visit.next_visit_date:
        child.next_visit_date = visit.next_visit_date
    child.save(update_fields=["current_color", "color_reasons", "color_updated_at", "next_visit_date"])
    if worse(old, visit.final_color):
        changes = ""
        if visit.weight:
            changes = f"vazn {visit.weight} g"
        return _create_alert(child=child, old=old, new=visit.final_color, reasons=visit.color_reasons,
                             changes=changes)
    return None


def set_subject_color(obj, color, reasons, *, child=False):
    """Scheduler uchun: ko'riksiz zona o'zgarishi (kelmadi, emlash kechikdi)."""
    old = obj.current_color
    if old == color and obj.color_reasons == reasons:
        return None
    obj.current_color, obj.color_reasons, obj.color_updated_at = color, reasons, timezone.now()
    obj.save(update_fields=["current_color", "color_reasons", "color_updated_at"])
    if worse(old, color):
        kw = {"child": obj} if child else {"patient": obj}
        return _create_alert(old=old, new=color, reasons=reasons, changes="", **kw)
    return None


def escalate(alert):
    alert.level = Alert.OVABMU
    alert.escalated = True
    alert.escalated_at = timezone.now()
    alert.save(update_fields=["level", "escalated", "escalated_at"])


def mark_seen(alert, user):
    if alert.status == Alert.NEW:
        alert.status, alert.seen_at, alert.seen_by = Alert.SEEN, timezone.now(), user
        alert.save(update_fields=["status", "seen_at", "seen_by"])


def resolve(alert, user, note, action_type=""):
    alert.status, alert.resolved_at, alert.resolved_by = Alert.RESOLVED, timezone.now(), user
    alert.action_type = action_type if action_type in dict(Alert.ACTION_CHOICES) else "other"
    alert.action_note = note
    if not alert.seen_at:
        alert.seen_at, alert.seen_by = alert.resolved_at, user
    alert.save()


def message_mother(patient, text, doctor):
    body = (f"👩‍⚕️ <b>Shifokoringizdan xabar</b>\n{esc(doctor.full_name or doctor.username)}, "
            f"{esc(patient.clinic.name)}\n\n{esc(text)}")
    return sender.send(patient.telegram_chat_id, body, kind="doctor_msg", recipient_label=f"{patient.short_name} (ona)",
                       patient=patient)


def notify_vaccination_done(vacc):
    c, m = vacc.child, vacc.child.mother
    body = (f"💉 <b>{esc(c.first_name)} emlandi</b>: {esc(vacc.vaccine.name)} ({vacc.done_date:%d.%m.%Y})\n"
            f"Himoya: {esc(vacc.vaccine.disease)}\n\n"
            "<b>Emlashdan keyingi parvarish:</b>\n"
            "• Poliklinikada 30 daqiqa kutib turing\n"
            "• Bolaga ko'proq suyuqlik (ko'krak suti yoki suv) bering\n"
            "• 2–3 kun yangi qo'shimcha ovqat kiritmang\n"
            "• Odam gavjum joylarga olib bormang\n"
            "• Harorat 38,5°C dan oshsa yoki bola bezovta bo'lsa — shifokorga murojaat qiling")
    return sender.send(m.telegram_chat_id, body, kind="reminder", recipient_label=f"{m.short_name} (ona)", patient=m)


__all__ = ["apply_mother_visit", "apply_child_visit", "set_subject_color", "escalate", "mark_seen", "resolve",
           "message_mother", "Notification", "YELLOW"]



def missed_reminder(kind, obj, doctor):
    """Ko'rik yoki emlashga kelmaganlarga xotirjam eslatma. kind: mother | child | vacc.

    recipient_label oxiridagi belgi (·m:id / ·c:id / ·v:id) — saytda «yuborilgan» holatini ko'rsatish uchun.
    """
    if kind == "mother":
        m, tag = obj, f"m:{obj.id}"
        text = (f"📅 <b>Ko'rik eslatmasi</b>\nHurmatli {esc(m.first_name)}, {obj.next_visit_date:%d.%m.%Y} kuni "
                f"belgilangan ko'rigingizga kelmadingiz.\nSiz va bo'lajak farzandingiz sog'lig'i uchun muntazam ko'rik "
                f"muhim — iltimos, imkon qadar tezroq {esc(m.clinic.name)}ga keling.")
    elif kind == "child":
        m, tag = obj.mother, f"c:{obj.id}"
        text = (f"📅 <b>Ko'rik eslatmasi</b>\nHurmatli {esc(m.first_name)}, farzandingiz <b>{esc(obj.first_name)}</b>ning "
                f"{obj.next_visit_date:%d.%m.%Y} kungi ko'rigiga kelmadingiz.\nBolaning o'sishi va rivojlanishini "
                f"kuzatish uchun iltimos, {esc(m.clinic.name)}ga keling.")
    else:
        m, tag = obj.child.mother, f"v:{obj.id}"
        text = (f"💉 <b>Emlash eslatmasi</b>\nHurmatli {esc(m.first_name)}, farzandingiz <b>{esc(obj.child.first_name)}</b>ning "
                f"<b>{esc(obj.vaccine.name)}</b> emlashi {obj.due_date:%d.%m.%Y} kuni bo'lishi kerak edi.\n"
                f"Emlash bolani xavfli kasalliklardan himoya qiladi — iltimos, {esc(m.clinic.name)}ga keling.")
    who = esc(doctor.full_name or doctor.username) if doctor else ""
    text += f"\n\nSavolingiz bo'lsa, shifokoringiz bilan bog'laning.\n👩‍⚕️ {who}"
    return sender.send(m.telegram_chat_id, text, kind="missed", recipient_label=f"{m.short_name} (ona) ·{tag}",
                       patient=m)


def missed_sent(tags, days=7):
    """Oxirgi N kunda eslatma yuborilganlar: {tag: sana}."""
    from datetime import timedelta
    from django.utils import timezone
    out = {}
    for label, at in Notification.objects.filter(kind="missed", created_at__gte=timezone.now() - timedelta(days=days)) \
            .values_list("recipient_label", "created_at"):
        t = label.rsplit("·", 1)[-1]
        if t in tags and t not in out:
            out[t] = at
    return out
