from django.db import models


class District(models.Model):
    """Tuman (Toshkent shahri tumanlari)."""
    name = models.CharField("Nomi", max_length=100, unique=True)
    population = models.PositiveIntegerField("Doimiy aholi (2025-yil 1-oktabr)", default=0)
    osm_id = models.BigIntegerField(null=True, blank=True)

    class Meta:
        verbose_name = "Tuman"
        verbose_name_plural = "Tumanlar"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Clinic(models.Model):
    """Oilaviy poliklinika."""
    district = models.ForeignKey(District, on_delete=models.CASCADE, related_name="clinics", verbose_name="Tuman")
    number = models.PositiveIntegerField("Raqami")
    name = models.CharField("Nomi", max_length=150)
    address = models.CharField("Manzil", max_length=255, blank=True)
    lat = models.FloatField(null=True, blank=True)
    lon = models.FloatField(null=True, blank=True)
    source = models.CharField("Manba", max_length=20, default="synthetic",
                              choices=[("osm", "OpenStreetMap"), ("synthetic", "Taxminiy")])
    osm_name = models.CharField("OSM'dagi nomi", max_length=200, blank=True)

    class Meta:
        verbose_name = "Poliklinika"
        verbose_name_plural = "Poliklinikalar"
        ordering = ["district__name", "number"]

    def __str__(self):
        return f"{self.name} ({self.district.name})"


class Mavze(models.Model):
    """Poliklinikaga biriktirilgan mavze (uchastka)."""
    clinic = models.ForeignKey(Clinic, on_delete=models.CASCADE, related_name="mavzes", verbose_name="Poliklinika")
    name = models.CharField("Nomi", max_length=100)

    class Meta:
        verbose_name = "Mavze"
        verbose_name_plural = "Mavzelar"
        ordering = ["clinic", "name"]

    def __str__(self):
        return f"{self.name} — {self.clinic.name}"


class ZoneSnapshot(models.Model):
    """Poliklinikaning oylik holati (oy oxiridagi yoki joriy oyda oxirgi hisoblangan): zonalar dinamikasi uchun.

    Tuman va shahar ko'rsatkichlari shu yozuvlar yig'indisidan hisoblanadi. Joriy oy yozuvini scheduler
    har soatda yangilaydi; oy tugagach u o'zgarmaydi va tarixga aylanadi.
    """
    clinic = models.ForeignKey(Clinic, on_delete=models.CASCADE, related_name="snapshots")
    month = models.DateField("Oy (1-sana)")
    p_total = models.PositiveIntegerField(default=0)
    p_red = models.PositiveIntegerField(default=0)
    p_yellow = models.PositiveIntegerField(default=0)
    demo = models.BooleanField("Demo tarix", default=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Oylik zona holati"
        verbose_name_plural = "Oylik zona holatlari"
        unique_together = [("clinic", "month")]
        ordering = ["month"]
