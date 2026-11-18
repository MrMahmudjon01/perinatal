"""Demo poliklinika (33-oilaviy) jamoasi: oilaviy shifokor (poliklinika_demo), ginekolog, pediatr, patronaj hamshira."""
from django.conf import settings
from django.core.management.base import BaseCommand

from apps.accounts.models import User

TEAM = [
    ("ginekolog_demo", User.GYN, "Saidova Gulnora Baxtiyorovna", "Akusher-ginekolog (ayollar maslahatxonasi)"),
    ("pediatr_demo", User.PED, "Toshmatov Jahongir Alisherovich", "Pediatr"),
    ("hamshira_demo", User.NURSE, "Ergasheva Zulfiya Rustamovna", "Patronaj hamshira (1-mavze)"),
]


class Command(BaseCommand):
    help = "Demo poliklinika jamoasini yaratadi/yangilaydi"

    def handle(self, *args, **opts):
        doc = User.objects.filter(username="poliklinika_demo").first()
        if not doc or not doc.clinic_id:
            self.stderr.write("poliklinika_demo topilmadi")
            return
        doc.clinic_role, doc.position = User.FAMILY, "Oilaviy shifokor (umumiy amaliyot)"
        doc.save(update_fields=["clinic_role", "position"])
        from apps.patients.models import Patient
        demo = Patient.objects.filter(last_name="Karimova", first_name="Dilnoza", mavze__clinic=doc.clinic).first()
        mavze = demo.mavze if demo else doc.clinic.mavzes.order_by("name").first()
        for username, crole, name, pos in TEAM:
            u, _ = User.objects.get_or_create(username=username, defaults={"role": User.CLINIC})
            u.role, u.clinic, u.district, u.clinic_role = User.CLINIC, doc.clinic, doc.district, crole
            u.full_name, u.position, u.is_active = name, pos, True
            u.mavze = mavze if crole == User.NURSE else None
            raw = settings.DEMO_PASSWORDS.get(username)
            if raw:
                u.set_password(raw)
            u.save()
            self.stdout.write(f"{username}: {u.get_clinic_role_display()}")
