from django.conf import settings
from django.db import models

from apps.patients.models import COLOR_CHOICES


class Alert(models.Model):
    """Avtomatik signal: bemor yoki chaqaloq zonasi yomonlashdi."""

    DISTRICT, OVABMU = "district", "ovabmu"
    LEVEL_CHOICES = [(DISTRICT, "Tuman shifokori"), (OVABMU, "OvaBMU")]
    NEW, SEEN, RESOLVED = "new", "seen", "resolved"
    STATUS_CHOICES = [(NEW, "Yangi"), (SEEN, "Ko'rildi"), (RESOLVED, "Chora ko'rildi")]

    patient = models.ForeignKey("patients.Patient", null=True, blank=True, on_delete=models.CASCADE,
                                related_name="alerts")
    child = models.ForeignKey("children.Child", null=True, blank=True, on_delete=models.CASCADE,
                              related_name="alerts")
    district = models.ForeignKey("geo.District", on_delete=models.CASCADE, related_name="alerts")
    clinic = models.ForeignKey("geo.Clinic", on_delete=models.CASCADE, related_name="alerts")

    from_color = models.CharField(max_length=10, choices=COLOR_CHOICES)
    to_color = models.CharField(max_length=10, choices=COLOR_CHOICES)
    reasons = models.JSONField(default=list)
    changes = models.CharField("Nima o'zgardi", max_length=255, blank=True)
    level = models.CharField(max_length=10, choices=LEVEL_CHOICES)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=NEW)
    escalated = models.BooleanField("Javobsizlik sababli ko'tarilgan", default=False)
    escalated_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    seen_at = models.DateTimeField(null=True, blank=True)
    seen_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                related_name="+")
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                    related_name="+")
    ACTION_CHOICES = [
        ("call", "Qo'ng'iroq qilindi"),
        ("consult", "Konsultatsiyaga chaqirildi"),
        ("hospital", "Statsionarga yotqizildi"),
        ("order", "Order berildi (perinatal markaz)"),
        ("observe", "Kuzatuvda qoldirildi"),
        ("other", "Boshqa"),
    ]
    action_type = models.CharField("Chora turi", max_length=12, choices=ACTION_CHOICES, blank=True)
    action_note = models.TextField("Ko'rilgan chora", blank=True)

    class Meta:
        indexes = [models.Index(fields=["level", "status"]), models.Index(fields=["created_at"]), ]
        verbose_name = "Signal"
        verbose_name_plural = "Signallar"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.subject_name}: {self.from_color} → {self.to_color}"

    @property
    def subject_name(self):
        return self.child.full_name if self.child_id else self.patient.full_name

    @property
    def response_minutes(self):
        """Signal yaratilgandan "ko'rildi"gacha o'tgan vaqt (daqiqa)."""
        if self.seen_at:
            return max(0, round((self.seen_at - self.created_at).total_seconds() / 60))
        return None

    @property
    def subject_kind(self):
        return "Chaqaloq" if self.child_id else "Homilador"

    @property
    def subject_url(self):
        from django.urls import reverse
        if self.child_id:
            return reverse("child_detail", args=[self.child_id])
        return reverse("patient_detail", args=[self.patient_id])


class Referral(models.Model):
    """Yo'llanma: poliklinika → tuman → OvaBMU."""

    DISTRICT, OVABMU = "district", "ovabmu"
    LEVEL_CHOICES = [(DISTRICT, "Tuman/shahar shifokori"), (OVABMU, "OvaBMU (order)")]
    ISSUED, ACCEPTED, ACTED = "issued", "accepted", "acted"
    STATUS_CHOICES = [(ISSUED, "Berildi"), (ACCEPTED, "Qabul qilindi"), (ACTED, "Harakat qilindi")]

    patient = models.ForeignKey("patients.Patient", null=True, blank=True, on_delete=models.CASCADE,
                                related_name="referrals")
    child = models.ForeignKey("children.Child", null=True, blank=True, on_delete=models.CASCADE,
                              related_name="referrals")
    district = models.ForeignKey("geo.District", on_delete=models.CASCADE, related_name="referrals")
    clinic = models.ForeignKey("geo.Clinic", on_delete=models.CASCADE, related_name="referrals")
    from_user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    to_level = models.CharField("Kimga", max_length=10, choices=LEVEL_CHOICES)
    reason = models.TextField("Sabab")
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=ISSUED)
    created_at = models.DateTimeField(auto_now_add=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    accepted_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                    related_name="+")
    acted_at = models.DateTimeField(null=True, blank=True)
    action_note = models.TextField("Natija", blank=True)

    class Meta:
        verbose_name = "Yo'llanma"
        verbose_name_plural = "Yo'llanmalar"
        ordering = ["-created_at"]

    @property
    def subject_name(self):
        return self.child.full_name if self.child_id else self.patient.full_name

    @property
    def subject_url(self):
        from django.urls import reverse
        if self.child_id:
            return reverse("child_detail", args=[self.child_id])
        return reverse("patient_detail", args=[self.patient_id])


class Notification(models.Model):
    """Telegram orqali yuborilgan (yoki navbatdagi) har bir xabar logi."""

    SENT, FAILED, NO_CHAT, NO_TOKEN = "sent", "failed", "no_chat", "no_token"
    STATUS_CHOICES = [(SENT, "Yuborildi"), (FAILED, "Xato"), (NO_CHAT, "Bot ulanmagan"),
                      (NO_TOKEN, "Bot token yo'q")]
    KIND_CHOICES = [("alert", "Signal"), ("reminder", "Eslatma"), ("doctor_msg", "Shifokor xabari"),
                    ("escalation", "Eskalatsiya"), ("referral", "Yo'llanma"), ("confirm", "Onaga yozuv (tasdiq so'raladi)"),
                    ("dispute", "Ona rad etdi"),
                    ("missed", "Kelmaganlik eslatmasi"), ("ai_chat", "AI yordamchi")]

    recipient_label = models.CharField(max_length=200)
    chat_id = models.BigIntegerField(null=True, blank=True)
    kind = models.CharField(max_length=20, choices=KIND_CHOICES)
    text = models.TextField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES)
    error = models.CharField(max_length=255, blank=True)
    patient = models.ForeignKey("patients.Patient", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["kind", "created_at"]), ]
        verbose_name = "Telegram xabar"
        verbose_name_plural = "Telegram xabarlar"
        ordering = ["-created_at"]


class MotherConfirmation(models.Model):
    """Onaga botda yuborilgan ko'rik / chora / yo'llanma xabari va onaning javobi (soxtalashtirishga qarshi).

    Shifokor kiritgan har bir yozuv onaga boradi; ona "Tasdiqlayman" yoki "Bunday bo'lmadi" deb javob beradi.
    Rad etilsa — yuqori bosqichga darhol xabar ketadi.
    """

    VISIT, CHILD_VISIT, ALERT, REFERRAL = "visit", "child_visit", "alert", "referral"
    KIND_CHOICES = [(VISIT, "Ko'rik"), (CHILD_VISIT, "Bola ko'rigi"), (ALERT, "Ko'rilgan chora"), (REFERRAL, "Yo'llanma")]

    kind = models.CharField(max_length=12, choices=KIND_CHOICES)
    object_id = models.PositiveBigIntegerField()
    patient = models.ForeignKey("patients.Patient", on_delete=models.CASCADE, related_name="confirmations")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                               related_name="+", verbose_name="Yozuv muallifi")
    summary = models.CharField(max_length=255)
    delivered = models.BooleanField("Onaga yetkazildi", default=False)
    confirmed = models.BooleanField("Ona javobi", null=True, blank=True)  # None — javob yo'q
    responded_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Ona tasdig'i"
        verbose_name_plural = "Ona tasdiqlari"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["kind", "object_id"])]

    @property
    def state(self):
        if self.confirmed is True:
            return "yes"
        if self.confirmed is False:
            return "no"
        return "wait" if self.delivered else "undelivered"
