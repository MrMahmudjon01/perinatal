import secrets

from django.contrib.auth.models import AbstractUser
from django.db import models


def _link_code():
    return secrets.token_hex(4).upper()


class User(AbstractUser):
    """Tizim foydalanuvchisi: poliklinika shifokori, tuman shifokori yoki OvaBMU mutaxassisi."""

    CLINIC = "clinic"
    DISTRICT = "district"
    OVABMU = "ovabmu"
    ROLE_CHOICES = [
        (CLINIC, "Poliklinika shifokori"),
        (DISTRICT, "Tuman/shahar shifokori"),
        (OVABMU, "OvaBMU mutaxassisi"),
    ]

    role = models.CharField("Rol", max_length=20, choices=ROLE_CHOICES, default=CLINIC)
    # Poliklinika ichidagi lavozim: kim nimani kiritadi (ruxsatlar scope.py da)
    FAMILY, GYN, PED, NURSE = "family", "gyn", "ped", "nurse"
    CLINIC_ROLE_CHOICES = [(FAMILY, "Oilaviy shifokor"), (GYN, "Akusher-ginekolog"), (PED, "Pediatr"),
                           (NURSE, "Patronaj hamshira")]
    clinic_role = models.CharField("Poliklinikadagi lavozimi", max_length=10, choices=CLINIC_ROLE_CHOICES,
                                   default=FAMILY, blank=True)
    mavze = models.ForeignKey("geo.Mavze", null=True, blank=True, on_delete=models.SET_NULL, related_name="nurses",
                              verbose_name="Biriktirilgan mavze (hamshira)")
    full_name = models.CharField("F.I.Sh.", max_length=150, blank=True)
    position = models.CharField("Lavozim", max_length=150, blank=True)
    phone = models.CharField("Telefon", max_length=20, blank=True)
    clinic = models.ForeignKey("geo.Clinic", null=True, blank=True, on_delete=models.SET_NULL,
                               related_name="doctors", verbose_name="Poliklinika")
    district = models.ForeignKey("geo.District", null=True, blank=True, on_delete=models.SET_NULL,
                                 related_name="doctors", verbose_name="Tuman")
    telegram_chat_id = models.BigIntegerField("Telegram chat ID", null=True, blank=True, unique=True)
    link_code = models.CharField("Bot ulash kodi", max_length=16, default=_link_code, unique=True)

    class Meta:
        verbose_name = "Foydalanuvchi"
        verbose_name_plural = "Foydalanuvchilar"

    def __str__(self):
        return self.full_name or self.username

    @property
    def role_label(self):
        """Ko'rsatish uchun: poliklinika xodimida — lavozimi (Pediatr, Patronaj hamshira...)."""
        if self.role == self.CLINIC and self.clinic_role:
            return self.get_clinic_role_display()
        return self.get_role_display()

    @property
    def scope_label(self):
        if self.role == self.CLINIC and self.clinic:
            return str(self.clinic)
        vc = getattr(self, "view_clinic_id", None)
        if vc and self.role in (self.DISTRICT, self.OVABMU):
            from apps.geo.models import Clinic
            c = Clinic.objects.select_related("district").filter(pk=vc).first()
            if c:
                return f"{c.district.name} tumani / {c.name}"
        if self.role == self.DISTRICT and self.district:
            return f"{self.district.name} tumani"
        vd = getattr(self, "view_district_id", None)
        if vd:
            from apps.geo.models import District
            d = District.objects.filter(pk=vd).first()
            if d:
                return f"Toshkent shahri / {d.name} tumani"
        return "Toshkent shahri"
