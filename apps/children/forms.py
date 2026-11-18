from django import forms

from apps.accounts.i18n import translate

from apps.patients.forms import DATE, OVERRIDE_CHOICES, BootstrapMixin

from .models import Child, ChildVisit, Vaccine, VaccinationSession
from .schedule import SPECIALISTS


class ChildForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = Child
        fields = ["first_name", "sex", "birth_date", "birth_weight", "birth_height", "apgar_1", "apgar_5",
                  "gestational_age_at_birth", "birth_notes"]
        widgets = {"birth_date": DATE}


class ChildVisitForm(BootstrapMixin, forms.ModelForm):
    specialists_seen = forms.MultipleChoiceField(
        label="Tor mutaxassislar ko'rigi (1, 3, 6, 12 oylikda)", required=False,
        choices=[(s, s) for s in SPECIALISTS], widget=forms.CheckboxSelectMultiple)
    color_choice = forms.ChoiceField(label="Zona", choices=OVERRIDE_CHOICES, initial="auto")
    source = forms.CharField(widget=forms.HiddenInput, required=False)
    transcript = forms.CharField(widget=forms.HiddenInput, required=False)
    ai_fields = forms.CharField(widget=forms.HiddenInput, required=False)

    class Meta:
        model = ChildVisit
        fields = ["visit_date", "visit_type", "weight", "height", "head_circ", "chest_circ", "temperature", "feeding",
                  "jaundice", "breathing_problem", "convulsions", "complaints", "diagnosis", "recommendation",
                  "next_visit_date", "color_override_note"]
        widgets = {"visit_date": DATE, "next_visit_date": DATE}

    def clean(self):
        d = super().clean()
        from apps.patients.forms import check_ranges
        check_ranges(self, d, "child")
        if d.get("color_choice") not in (None, "auto") and not d.get("color_override_note"):
            self.add_error("color_override_note", translate("Zonani o'zgartirsangiz, sababini yozing", self.lang))
        return d


class VaccinationSessionForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = VaccinationSession
        fields = ["vaccine", "date", "time", "room", "note"]
        widgets = {"date": DATE, "time": forms.TimeInput(attrs={"type": "time"}, format="%H:%M")}

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.fields["vaccine"].queryset = Vaccine.objects.order_by("age_days", "code")
        self.fields["vaccine"].label_from_instance = lambda v: f"{v.code} — {v.name} ({v.age_label})"

    def clean_date(self):
        from datetime import date
        d = self.cleaned_data["date"]
        if d <= date.today():
            raise forms.ValidationError(translate("Sana kelajakda bo'lishi kerak", self.lang))
        return d
