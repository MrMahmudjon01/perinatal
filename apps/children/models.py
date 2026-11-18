from datetime import date, timedelta

from django.conf import settings
from django.db import models

from apps.patients.models import COLOR_CHOICES, GREEN


class Child(models.Model):
    """Chaqaloq (onaga bog'langan)."""

    SEX_CHOICES = [("m", "O'g'il"), ("f", "Qiz")]

    mother = models.ForeignKey("patients.Patient", on_delete=models.CASCADE, related_name="children",
                               verbose_name="Ona")
    first_name = models.CharField("Ism", max_length=80)
    sex = models.CharField("Jinsi", max_length=1, choices=SEX_CHOICES)
    birth_date = models.DateField("Tug'ilgan sana")
    birth_weight = models.PositiveIntegerField("Tug'ilgandagi vazn, g")
    birth_height = models.PositiveSmallIntegerField("Tug'ilgandagi bo'y, sm", null=True, blank=True)
    apgar_1 = models.PositiveSmallIntegerField("Apgar (1 daq.)", null=True, blank=True)
    apgar_5 = models.PositiveSmallIntegerField("Apgar (5 daq.)", null=True, blank=True)
    gestational_age_at_birth = models.PositiveSmallIntegerField("Tug'ilgandagi muddat, hafta", null=True, blank=True)
    birth_notes = models.TextField("Tug'ruq haqida izoh", blank=True)

    current_color = models.CharField("Joriy zona", max_length=10, choices=COLOR_CHOICES, default=GREEN)
    color_reasons = models.JSONField("Zona sabablari", default=list, blank=True)
    color_updated_at = models.DateTimeField(null=True, blank=True)
    next_visit_date = models.DateField("Keyingi ko'rik", null=True, blank=True)
    visit_reminder_for = models.DateField("Eslatma yuborilgan ko'rik sanasi", null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["birth_date"]), models.Index(fields=["next_visit_date"]), models.Index(fields=["current_color"]), ]
        verbose_name = "Chaqaloq"
        verbose_name_plural = "Chaqaloqlar"
        ordering = ["-birth_date"]

    def __str__(self):
        return self.full_name

    @property
    def full_name(self):
        surname = self.mother.last_name
        if self.sex == "m" and surname.endswith("a"):
            surname = surname[:-1]
        return f"{surname} {self.first_name}"

    @property
    def age_days(self):
        return (date.today() - self.birth_date).days

    @property
    def age_label(self):
        d = self.age_days
        if d < 31:
            return f"{d} kunlik"
        m = d // 30
        if m < 24:
            return f"{m} oylik"
        return f"{d // 365} yosh"

    @property
    def mavze(self):
        return self.mother.mavze


class ChildVisit(models.Model):
    """Chaqaloq ko'rigi (patronaj yoki poliklinikada)."""

    FEEDING_CHOICES = [("breast", "Ko'krak suti"), ("mixed", "Aralash"), ("formula", "Sun'iy"),
                       ("poor", "Yomon emadi")]
    SOURCE_CHOICES = [("manual", "Qo'lda"), ("voice", "Ovoz (AI)"), ("mixed", "Ovoz + qo'lda")]

    child = models.ForeignKey(Child, on_delete=models.CASCADE, related_name="visits")
    doctor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                               related_name="child_visits", verbose_name="Shifokor")
    visit_date = models.DateField("Ko'rik sanasi", default=date.today)
    weight = models.PositiveIntegerField("Vazn, g", null=True, blank=True)
    height = models.PositiveSmallIntegerField("Bo'y, sm", null=True, blank=True)
    temperature = models.DecimalField("Harorat, °C", max_digits=4, decimal_places=1, null=True, blank=True)
    feeding = models.CharField("Ovqatlanish", max_length=10, choices=FEEDING_CHOICES, blank=True)
    jaundice = models.BooleanField("Sariqlik", default=False)
    breathing_problem = models.BooleanField("Nafas olish qiyinligi", default=False)
    convulsions = models.BooleanField("Tutqanoq", default=False)
    head_circ = models.DecimalField("Bosh aylanasi, sm", max_digits=4, decimal_places=1, null=True, blank=True)
    chest_circ = models.DecimalField("Ko'krak aylanasi, sm", max_digits=4, decimal_places=1, null=True, blank=True)
    visit_type = models.CharField("Ko'rik turi", max_length=12, default="monthly",
                                  choices=[("patronage", "Patronaj (uyda)"), ("monthly", "Oylik rejali"),
                                           ("sick", "Kasallik bo'yicha")])
    specialists = models.JSONField("Tor mutaxassislar ko'rigi", default=list, blank=True)
    complaints = models.TextField("Shikoyatlar / ko'rik", blank=True)
    diagnosis = models.CharField("Tashxis / xulosa", max_length=255, blank=True)
    recommendation = models.TextField("Tavsiya", blank=True)
    next_visit_date = models.DateField("Keyingi ko'rik sanasi", null=True, blank=True)

    source = models.CharField("Kiritish usuli", max_length=10, choices=SOURCE_CHOICES, default="manual")
    transcript = models.TextField("Ovoz matni", blank=True)
    ai_fields = models.JSONField(default=dict, blank=True)

    computed_color = models.CharField(max_length=10, choices=COLOR_CHOICES, default=GREEN)
    final_color = models.CharField("Tasdiqlangan zona", max_length=10, choices=COLOR_CHOICES, default=GREEN)
    color_reasons = models.JSONField(default=list, blank=True)
    color_override_note = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["child", "visit_date"]), ]
        verbose_name = "Chaqaloq ko'rigi"
        verbose_name_plural = "Chaqaloq ko'riklari"
        ordering = ["-visit_date", "-created_at"]


class Vaccine(models.Model):
    """Milliy emlash kalendaridagi vaksina (yoshi kunlarda)."""
    code = models.CharField("Kod", max_length=20, unique=True)
    name = models.CharField("Nomi", max_length=150)
    disease = models.CharField("Qaysi kasallikdan", max_length=200, blank=True)
    age_days = models.PositiveIntegerField("Emlash yoshi (kun)")
    age_label = models.CharField("Yosh (matn)", max_length=50)

    class Meta:
        verbose_name = "Vaksina"
        verbose_name_plural = "Emlash kalendari"
        ordering = ["age_days", "code"]

    def __str__(self):
        return f"{self.code} — {self.name}"


class ChildVaccination(models.Model):
    """Bolaning konkret emlashi: reja va bajarilishi."""

    PLANNED, DONE, OVERDUE = "planned", "done", "overdue"
    STATUS_CHOICES = [(PLANNED, "Rejada"), (DONE, "Bajarildi"), (OVERDUE, "Kechikdi")]

    child = models.ForeignKey(Child, on_delete=models.CASCADE, related_name="vaccinations")
    vaccine = models.ForeignKey(Vaccine, on_delete=models.PROTECT, related_name="+")
    due_date = models.DateField("Reja sanasi")
    done_date = models.DateField("Bajarilgan sana", null=True, blank=True)
    status = models.CharField("Holat", max_length=10, choices=STATUS_CHOICES, default=PLANNED)
    batch = models.CharField("Seriya", max_length=50, blank=True)
    reaction = models.CharField("Reaksiya", max_length=200, blank=True)
    done_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                related_name="+")
    reminder_sent = models.BooleanField(default=False)

    class Meta:
        indexes = [models.Index(fields=["status", "due_date"]), ]
        verbose_name = "Emlash"
        verbose_name_plural = "Emlashlar"
        ordering = ["due_date", "vaccine__code"]
        unique_together = [("child", "vaccine")]

    def __str__(self):
        return f"{self.child} — {self.vaccine.code}"


def create_vaccination_plan(child):
    """Bola qo'shilganda butun emlash rejasini yaratadi."""
    today = date.today()
    items = []
    for v in Vaccine.objects.all():
        due = child.birth_date + timedelta(days=v.age_days)
        status = ChildVaccination.OVERDUE if due < today - timedelta(days=7) else ChildVaccination.PLANNED
        items.append(ChildVaccination(child=child, vaccine=v, due_date=due, status=status))
    ChildVaccination.objects.bulk_create(items, ignore_conflicts=True)


class VaccinationSession(models.Model):
    """Poliklinika e'lon qilgan emlash kuni: vaksina (milliy kalendardan), sana va vaqt.

    E'lon yaratilganda shu vaksinaga mos (yoshi yetgan, hali olmagan) bolalar avtomatik taklif qilinadi;
    bot onalarga 3 kun va 1 kun qolganda eslatma yuboradi.
    """

    PLANNED, DONE, CANCELLED = "planned", "done", "cancelled"
    STATUS_CHOICES = [(PLANNED, "Rejada"), (DONE, "O'tkazildi"), (CANCELLED, "Bekor qilindi")]

    clinic = models.ForeignKey("geo.Clinic", on_delete=models.CASCADE, related_name="vaccination_sessions",
                               verbose_name="Poliklinika")
    vaccine = models.ForeignKey(Vaccine, on_delete=models.PROTECT, related_name="+", verbose_name="Vaksina")
    date = models.DateField("Emlash sanasi")
    time = models.TimeField("Vaqti", default="09:00")
    room = models.CharField("Xona / joy", max_length=100, blank=True, default="Emlash xonasi")
    note = models.CharField("Izoh", max_length=255, blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=PLANNED)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Emlash e'loni"
        verbose_name_plural = "Emlash e'lonlari"
        ordering = ["-date", "-time"]

    def __str__(self):
        return f"{self.vaccine.code} — {self.date:%d.%m.%Y} {self.time:%H:%M}"

    @property
    def days_left(self):
        return (self.date - date.today()).days


class SessionInvite(models.Model):
    """E'longa mos keladigan bola va eslatmalar holati."""

    session = models.ForeignKey(VaccinationSession, on_delete=models.CASCADE, related_name="invites")
    child = models.ForeignKey(Child, on_delete=models.CASCADE, related_name="session_invites")
    vaccination = models.ForeignKey(ChildVaccination, on_delete=models.CASCADE, related_name="+")
    reminder3_at = models.DateTimeField("3 kun oldin eslatma", null=True, blank=True)
    reminder1_at = models.DateTimeField("1 kun oldin eslatma", null=True, blank=True)
    attended = models.BooleanField("Emlandi", default=False)

    class Meta:
        unique_together = [("session", "child")]
        ordering = ["child__birth_date"]


def eligible_children(clinic, vaccine, on_date):
    """Shu vaksinaga mos bolalar: poliklinikaga tegishli, 2 yoshgacha, emlash yoshi e'lon sanasigacha yetgan,
    hali olmagan (rejada yoki kechikkan) va boshqa rejadagi e'longa taklif qilinmagan."""
    already = SessionInvite.objects.filter(session__status=VaccinationSession.PLANNED, session__vaccine=vaccine,
                                           attended=False).values_list("child_id", flat=True)
    return (ChildVaccination.objects
            .filter(vaccine=vaccine, status__in=[ChildVaccination.PLANNED, ChildVaccination.OVERDUE],
                    due_date__lte=on_date, child__mother__mavze__clinic=clinic,
                    child__birth_date__gte=on_date - timedelta(days=2 * 365))
            .exclude(child_id__in=already)
            .select_related("child__mother"))
