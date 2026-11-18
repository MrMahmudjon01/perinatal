""".env dagi PASS_* parollarni qo'llaydi (ma'lumotni qayta yaratmasdan). Qolgan demo hisoblarga kirish yopiladi."""
from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.core.management.base import BaseCommand

from apps.accounts.models import User


class Command(BaseCommand):
    def handle(self, *a, **kw):
        pw = {k: v for k, v in settings.DEMO_PASSWORDS.items() if v}
        if not pw:
            self.stderr.write(".env da PASS_* yo'q")
            return
        closed = User.objects.exclude(username__in=pw).update(password=make_password(None))
        for uname, raw in pw.items():
            n = User.objects.filter(username=uname).update(password=make_password(raw))
            self.stdout.write(f"{uname}: {'ok' if n else 'topilmadi'}")
        self.stdout.write(f"Boshqa {closed} ta demo hisobga kirish yopildi")
