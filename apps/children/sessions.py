"""Emlash e'lonlari: bolalarni taklif qilish va onalarga bot orqali eslatma (3 kun va 1 kun qolganda)."""
import html

from django.utils import timezone

from apps.bot import sender

from .models import SessionInvite, VaccinationSession, eligible_children

WEEKDAYS = ["dushanba", "seshanba", "chorshanba", "payshanba", "juma", "shanba", "yakshanba"]


def esc(s):
    return html.escape(str(s), quote=False)


def invite_eligible(session):
    """Mos bolalarni e'longa qo'shadi. Qaytaradi: qo'shilganlar soni."""
    rows = [SessionInvite(session=session, child=v.child, vaccination=v)
            for v in eligible_children(session.clinic, session.vaccine, session.date)]
    SessionInvite.objects.bulk_create(rows, ignore_conflicts=True)
    return len(rows)


def _text(inv, kind):
    s, c = inv.session, inv.child
    when = f"{s.date:%d.%m.%Y} ({WEEKDAYS[s.date.weekday()]}) soat <b>{s.time:%H:%M}</b>"
    place = f"{esc(s.clinic.name)}" + (f", {esc(s.room)}" if s.room else "")
    if kind == "r3":
        return (f"💉 <b>Emlash eslatmasi</b>\n{when} da farzandingiz <b>{esc(c.first_name)}</b> uchun "
                f"<b>{esc(s.vaccine.name)}</b> emlashi bor.\nHimoya: {esc(s.vaccine.disease)}\n🏥 {place}\n\n"
                f"Esdan chiqarmang! Emlash pasportini olib keling.")
    return (f"⏰ <b>Ertaga emlash!</b>\nErtaga — {when} da <b>{place}</b>ga keling.\n"
            f"👶 {esc(c.first_name)} — {esc(s.vaccine.name)}\n\n"
            f"Bolada isitma yoki shamollash belgilari bo'lsa, emlashdan oldin shifokorga ayting.")


def send_reminders(today=None):
    """Scheduler har tsiklda chaqiradi. 3 kun (yoki kamroq) qolganda — eslatma, 1 kun qolganda — "ertaga"."""
    today = today or timezone.localdate()
    sent = 0
    qs = SessionInvite.objects.filter(session__status=VaccinationSession.PLANNED, session__date__gt=today,
                                      attended=False).select_related("session__clinic", "session__vaccine",
                                                                     "child__mother")
    for inv in qs:
        left = (inv.session.date - today).days
        m = inv.child.mother
        if left == 1 and not inv.reminder1_at:
            sender.send(m.telegram_chat_id, _text(inv, "r1"), kind="reminder", recipient_label=f"{m.short_name} (ona)",
                        patient=m)
            inv.reminder1_at = timezone.now()
            inv.reminder3_at = inv.reminder3_at or inv.reminder1_at  # kech e'lon qilinganda 3-kunlik o'tkazib yuboriladi
            inv.save(update_fields=["reminder1_at", "reminder3_at"])
            sent += 1
        elif 1 < left <= 3 and not inv.reminder3_at:
            sender.send(m.telegram_chat_id, _text(inv, "r3"), kind="reminder", recipient_label=f"{m.short_name} (ona)",
                        patient=m)
            inv.reminder3_at = timezone.now()
            inv.save(update_fields=["reminder3_at"])
            sent += 1
    return sent
