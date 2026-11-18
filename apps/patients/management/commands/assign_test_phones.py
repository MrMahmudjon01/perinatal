"""Test uchun haqiqiy telefon raqamlarini demo onalarga biriktiradi (botga ulanib sinash uchun).

.env: TEST_PHONES=+998901234567,+998901234568,+998901234569
Tartib: 1) Karimova Dilnoza — homilador, yashil, farzandi Aziz
        2) Yusupova Madina — yaqinda tug'gan, chaqaloq Sevara (emlash eslatmalari, bola ko'riklari)
        3) Rahimova Umida — homilador, QIZIL zona (signal, chora, AI xulosa)
        4) Qodirova Sabina — homilador, SARIQ zona
Hammasi 33-oilaviy poliklinika, 1-mavze (poliklinika_demo). Seed_demo oxirida avtomatik chaqiriladi.
"""
import os

from django.core.management.base import BaseCommand

from apps.patients.models import Patient

TARGETS = [("Karimova", "Dilnoza"), ("Yusupova", "Madina"), ("Rahimova", "Umida"), ("Qodirova", "Sabina")]


class Command(BaseCommand):
    help = "TEST_PHONES raqamlarini demo onalarga biriktiradi"

    def handle(self, *args, **opts):
        phones = [p.strip() for p in os.environ.get("TEST_PHONES", "").split(",") if p.strip()]
        demo = Patient.objects.filter(phone=os.environ.get("DEMO_MOTHER_PHONE", "")).first() \
            or Patient.objects.filter(last_name="Karimova", first_name="Dilnoza").first()
        if not demo:
            self.stderr.write("Demo mavze topilmadi")
            return
        for phone, (last, first) in zip(phones, TARGETS):
            p = Patient.objects.filter(mavze=demo.mavze, last_name=last, first_name=first).first()
            if not p:
                self.stderr.write(f"{last} {first} topilmadi")
                continue
            if p.phone == phone:
                self.stdout.write(f"{phone} → {p.short_name} (o'zgarishsiz)")
                continue
            other = Patient.objects.filter(phone=phone).exclude(pk=p.pk).first()
            if other:  # raqam boshqa (tasodifiy) bemorda bo'lsa — unga yangi raqam
                other.phone, other.telegram_chat_id = f"+99899{other.pk % 10000000:07d}", None
                other.save(update_fields=["phone", "telegram_chat_id"])
            p.phone, p.telegram_chat_id = phone, None
            p.save(update_fields=["phone", "telegram_chat_id"])
            self.stdout.write(f"{phone} → {p.short_name} ({p.get_status_display()}, {p.current_color})")
