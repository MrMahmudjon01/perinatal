"""Fon vazifalari (har daqiqada):
1. Javobsiz signallarni OvaBMU ga ko'tarish (eskalatsiya)
2. Muddati o'tgan emlashlarni "kechikdi" deb belgilash va bola zonasini yangilash
3. Ko'rikka kelmaganlarni aniqlash va zonani yangilash (patronaj ro'yxatiga tushadi)
4. Onalarga ertangi qabul eslatmasi; emlash e'lonlari bo'yicha 3 kun va 1 kun oldin eslatma

python manage.py run_scheduler          # doimiy ishlaydi
python manage.py run_scheduler --once   # bir marta
"""
import html
import time
from datetime import date, timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import close_old_connections
from django.utils import timezone

from apps.alerts import services
from apps.alerts.models import Alert
from apps.bot import sender
from apps.children.models import Child, ChildVaccination
from apps.patients.models import Patient
from apps.risk.recompute import recompute_child, recompute_patient

VACC_GRACE_DAYS = 7
MISSED_LABEL = "Ko'rikka kelmadi"


def esc(s):
    return html.escape(str(s), quote=False)


class Command(BaseCommand):
    help = "Eskalatsiya, emlash va ko'rik nazorati, eslatmalar"

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true")
        parser.add_argument("--interval", type=int, default=60)

    def handle(self, *args, once=False, interval=60, **kw):
        self.stdout.write(f"Scheduler ishga tushdi (eskalatsiya: {settings.ALERT_ESCALATION_MINUTES} daq.)")
        while True:
            close_old_connections()
            try:
                stats = self.tick()
                if any(stats.values()):
                    self.stdout.write(f"[{timezone.localtime():%H:%M:%S}] {stats}")
            except Exception as e:  # sikl to'xtab qolmasligi kerak
                self.stderr.write(f"Xato: {e!r}")
            if once:
                return
            time.sleep(interval)

    def tick(self):
        return {
            "escalated": self.escalate(),
            "vacc_overdue": self.vaccinations_overdue(),
            "missed": self.missed_visits(),
            "reminders": self.reminders(),
            "snapshot": self.snapshot(),
        }

    _last_snapshot = None

    def snapshot(self):
        """Joriy oy zona holatini soatiga bir marta saqlaydi (Dinamika sahifasi uchun)."""
        now = timezone.now()
        if self._last_snapshot and (now - self._last_snapshot).total_seconds() < 3600:
            return 0
        from apps.dashboard.history import snapshot_current
        self._last_snapshot = now
        snapshot_current()
        return 0

    def escalate(self):
        cutoff = timezone.now() - timedelta(minutes=settings.ALERT_ESCALATION_MINUTES)
        qs = Alert.objects.filter(level=Alert.DISTRICT, status=Alert.NEW, escalated=False, created_at__lt=cutoff)
        n = 0
        for a in qs.select_related("patient", "child", "clinic", "district"):
            services.escalate(a)
            n += 1
        return n

    def vaccinations_overdue(self):
        limit = date.today() - timedelta(days=VACC_GRACE_DAYS)
        qs = ChildVaccination.objects.filter(status=ChildVaccination.PLANNED, due_date__lt=limit)
        child_ids = set(qs.values_list("child_id", flat=True))
        qs.update(status=ChildVaccination.OVERDUE)
        for c in Child.objects.filter(id__in=child_ids):
            recompute_child(c)
        return len(child_ids)

    def missed_visits(self):
        today = date.today()
        n = 0
        for p in Patient.objects.filter(status=Patient.PREGNANT, next_visit_date__lt=today) \
                .exclude(color_reasons__contains=[MISSED_LABEL]):
            recompute_patient(p)
            n += 1
        for c in Child.objects.filter(next_visit_date__lt=today, birth_date__gte=today - timedelta(days=2 * 365)) \
                .exclude(color_reasons__contains=[MISSED_LABEL]):
            recompute_child(c)
            n += 1
        return n

    def reminders(self):
        tomorrow = date.today() + timedelta(days=1)
        n = 0
        for p in Patient.objects.filter(status=Patient.PREGNANT, next_visit_date=tomorrow) \
                .exclude(visit_reminder_for=tomorrow).select_related("mavze__clinic"):
            text = (f"📅 <b>Eslatma</b>\nHurmatli {esc(p.first_name)}, ertaga ({tomorrow:%d.%m.%Y}) "
                    f"{esc(p.mavze.clinic.name)}da navbatdagi ko'rigingiz bor.\n"
                    f"Iltimos, o'z vaqtida keling. Sog'lig'ingiz — farzandingiz sog'lig'i!")
            sender.send(p.telegram_chat_id, text, kind="reminder", recipient_label=f"{p.short_name} (ona)", patient=p)
            p.visit_reminder_for = tomorrow
            p.save(update_fields=["visit_reminder_for"])
            n += 1
        # Emlash eslatmalari endi poliklinika e'loni bo'yicha (3 kun va 1 kun qolganda)
        from apps.children.sessions import send_reminders
        n += send_reminders()
        for c in Child.objects.filter(next_visit_date=tomorrow).exclude(visit_reminder_for=tomorrow) \
                .select_related("mother__mavze__clinic"):
            m = c.mother
            text = (f"📅 <b>Eslatma</b>\nErtaga ({tomorrow:%d.%m.%Y}) farzandingiz "
                    f"<b>{esc(c.first_name)}</b>ning navbatdagi ko'rigi.\n🏥 {esc(m.mavze.clinic.name)}")
            sender.send(m.telegram_chat_id, text, kind="reminder", recipient_label=f"{m.short_name} (ona)", patient=m)
            c.visit_reminder_for = tomorrow
            c.save(update_fields=["visit_reminder_for"])
            n += 1
        return n
