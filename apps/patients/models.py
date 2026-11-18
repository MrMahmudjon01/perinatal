from datetime import date, timedelta

from django.conf import settings
from django.db import models

GREEN, YELLOW, RED = "green", "yellow", "red"
COLOR_CHOICES = [(GREEN, "Yashil"), (YELLOW, "Sariq"), (RED, "Qizil")]


class Patient(models.Model):
    """Ro'yxatdagi homilador ayol (tug'gandan keyin ham ona sifatida qoladi)."""

    PREGNANT = "pregnant"
    DELIVERED = "delivered"
    CLOSED = "closed"
    STATUS_CHOICES = [(PREGNANT, "Homilador"), (DELIVERED, "Tug'di"), (CLOSED, "Kuzatuv yopilgan")]

    BLOOD_CHOICES = [(b, b) for b in ["O(I) Rh+", "O(I) Rh-", "A(II) Rh+", "A(II) Rh-",
                                       "B(III) Rh+", "B(III) Rh-", "AB(IV) Rh+", "AB(IV) Rh-"]]

    last_name = models.CharField("Familiya", max_length=80)
    first_name = models.CharField("Ism", max_length=80)
    middle_name = models.CharField("Otasining ismi", max_length=80, blank=True)
    birth_date = models.DateField("Tug'ilgan sana")
    phone = models.CharField("Telefon", max_length=20, unique=True,
                             help_text="+998XXXXXXXXX — Telegram bot shu raqam orqali bog'lanadi")
    address = models.CharField("Manzil", max_length=255, blank=True)
    mavze = models.ForeignKey("geo.Mavze", on_delete=models.PROTECT, related_name="patients", verbose_name="Mavze")

    lmp_date = models.DateField("Oxirgi hayz sanasi", null=True, blank=True)
    gravidity = models.PositiveSmallIntegerField("Nechanchi homiladorlik", default=1)
    parity = models.PositiveSmallIntegerField("Tug'ruqlar soni", default=0)
    blood_group = models.CharField("Qon guruhi", max_length=12, choices=BLOOD_CHOICES, blank=True)
    chronic_conditions = models.TextField("Surunkali kasalliklar", blank=True)
    previous_complications = models.TextField("Oldingi homiladorlik asoratlari", blank=True)

    status = models.CharField("Holat", max_length=20, choices=STATUS_CHOICES, default=PREGNANT)
    delivered_at = models.DateField("Tug'ruq sanasi", null=True, blank=True)

    current_color = models.CharField("Joriy zona", max_length=10, choices=COLOR_CHOICES, default=GREEN)
    color_reasons = models.JSONField("Zona sabablari", default=list, blank=True)
    color_updated_at = models.DateTimeField(null=True, blank=True)
    next_visit_date = models.DateField("Keyingi ko'rik", null=True, blank=True)

    telegram_chat_id = models.BigIntegerField("Telegram chat ID", null=True, blank=True, unique=True)
    visit_reminder_for = models.DateField("Eslatma yuborilgan ko'rik sanasi", null=True, blank=True)
    registered_at = models.DateField("Ro'yxatga olingan", default=date.today)
    consent = models.BooleanField("Shaxsiy ma'lumotlarni qayta ishlashga rozilik olingan", default=False,
                                  help_text="Ona yozma/og'zaki rozilik berdi (ZRU-547)")
    consent_at = models.DateField("Rozilik sanasi", null=True, blank=True)

    class Meta:
        verbose_name = "Homilador ayol"
        verbose_name_plural = "Homilador ayollar"
        ordering = ["last_name", "first_name"]
        indexes = [models.Index(fields=["status", "next_visit_date"]), models.Index(fields=["registered_at"]), models.Index(fields=["status", "current_color"])]

    def __str__(self):
        return self.full_name

    @property
    def full_name(self):
        return " ".join(p for p in [self.last_name, self.first_name, self.middle_name] if p)

    @property
    def short_name(self):
        return f"{self.last_name} {self.first_name}"

    @property
    def age(self):
        t = date.today()
        b = self.birth_date
        return t.year - b.year - ((t.month, t.day) < (b.month, b.day))

    @property
    def gestational_weeks(self):
        if not self.lmp_date or self.status != self.PREGNANT:
            return None
        return (date.today() - self.lmp_date).days // 7

    @property
    def edd(self):
        """Kutilayotgan tug'ruq sanasi (Negele qoidasi: OHS + 280 kun)."""
        return self.lmp_date + timedelta(days=280) if self.lmp_date else None

    @property
    def missed_visit(self):
        return bool(self.next_visit_date and self.next_visit_date < date.today()
                    and self.status == self.PREGNANT)

    @property
    def clinic(self):
        return self.mavze.clinic

    @property
    def district(self):
        return self.mavze.clinic.district


class Visit(models.Model):
    """Homilador ayolning ko'rigi va tahlil natijalari."""

    PROTEIN_CHOICES = [("none", "Yo'q"), ("trace", "Izlari"), ("+", "+"), ("++", "++"), ("+++", "+++")]
    MOVEMENT_CHOICES = [("normal", "Normal"), ("decreased", "Sustlashgan"), ("absent", "Yo'q"),
                        ("na", "Hali sezilmaydi")]
    SOURCE_CHOICES = [("manual", "Qo'lda"), ("voice", "Ovoz (AI)"), ("mixed", "Ovoz + qo'lda")]

    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name="visits")
    doctor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                               related_name="visits", verbose_name="Shifokor")
    visit_date = models.DateField("Ko'rik sanasi", default=date.today)

    gestational_week = models.PositiveSmallIntegerField("Homiladorlik haftasi", null=True, blank=True)
    bp_sys = models.PositiveSmallIntegerField("Qon bosimi (sistolik)", null=True, blank=True)
    bp_dia = models.PositiveSmallIntegerField("Qon bosimi (diastolik)", null=True, blank=True)
    hb = models.PositiveSmallIntegerField("Gemoglobin, g/l", null=True, blank=True)
    urine_protein = models.CharField("Siydikda oqsil", max_length=10, choices=PROTEIN_CHOICES, blank=True)
    fetal_movement = models.CharField("Homila harakati", max_length=12, choices=MOVEMENT_CHOICES, blank=True)
    fetal_heart_rate = models.PositiveSmallIntegerField("Homila yurak urishi (1 daq.)", null=True, blank=True)
    weight = models.DecimalField("Vazn, kg", max_digits=5, decimal_places=1, null=True, blank=True)
    temperature = models.DecimalField("Harorat, °C", max_digits=4, decimal_places=1, null=True, blank=True)
    edema = models.BooleanField("Shish (oyoq/yuz)", default=False)
    bleeding = models.BooleanField("Qon ketishi", default=False)
    headache_vision = models.BooleanField("Kuchli bosh og'rig'i / ko'rish buzilishi", default=False)

    complaints = models.TextField("Shikoyatlar", blank=True)
    complications = models.TextField("Asoratlar / anamnez", blank=True)
    diagnosis = models.CharField("Tashxis / xulosa", max_length=255, blank=True)
    recommendation = models.TextField("Tavsiya", blank=True)
    next_visit_date = models.DateField("Keyingi ko'rik sanasi", null=True, blank=True)

    source = models.CharField("Kiritish usuli", max_length=10, choices=SOURCE_CHOICES, default="manual")
    transcript = models.TextField("Ovoz matni", blank=True)
    ai_fields = models.JSONField("AI ajratgan maydonlar", default=dict, blank=True)

    computed_color = models.CharField("Tizim hisoblagan zona", max_length=10, choices=COLOR_CHOICES, default=GREEN)
    final_color = models.CharField("Tasdiqlangan zona", max_length=10, choices=COLOR_CHOICES, default=GREEN)
    color_reasons = models.JSONField("Zona sabablari", default=list, blank=True)
    color_override_note = models.CharField("Zonani o'zgartirish sababi", max_length=255, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["patient", "visit_date"]), ]
        verbose_name = "Ko'rik"
        verbose_name_plural = "Ko'riklar"
        ordering = ["-visit_date", "-created_at"]

    def __str__(self):
        return f"{self.patient.short_name} — {self.visit_date}"

    @property
    def bp(self):
        return f"{self.bp_sys}/{self.bp_dia}" if self.bp_sys and self.bp_dia else ""



class AccessLog(models.Model):
    """Audit jurnali: kim, qachon, qaysi bemor kartasini ochdi yoki o'zgartirdi (tibbiy sir va ZRU-547 uchun)."""
    VIEW, EDIT, VISIT, AI, MESSAGE, CREATE = "view", "edit", "visit", "ai", "message", "create"
    ACTION_CHOICES = [(VIEW, "Kartani ko'rdi"), (CREATE, "Ro'yxatga oldi"), (EDIT, "Ma'lumotni tahrirladi"),
                      (VISIT, "Ko'rik kiritdi"), (AI, "AI xulosa so'radi"), (MESSAGE, "Onaga xabar yubordi")]
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name="access_logs")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    action = models.CharField(max_length=10, choices=ACTION_CHOICES)
    ip = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "Audit yozuvi"
        verbose_name_plural = "Audit jurnali"
        ordering = ["-created_at"]

    @classmethod
    def log(cls, request, patient, action):
        from apps.accounts.security import client_ip
        try:
            ip = client_ip(request)
        except Exception:
            ip = None
        return cls.objects.create(patient=patient, user=request.user, action=action, ip=ip or None)
