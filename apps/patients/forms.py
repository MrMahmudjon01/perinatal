from django import forms

from apps.accounts.i18n import translate

from apps.geo.models import Mavze

from .models import COLOR_CHOICES, Patient, Visit


def _tr_label(label, lang):
    label = str(label)
    if ": " in label:  # "O'zgartirish: Qizil" kabi tarkibiy yorliqlar
        a, b = label.split(": ", 1)
        return f"{translate(a, lang)}: {translate(b, lang)}"
    return translate(label, lang)


class BootstrapMixin:
    def __init__(self, *a, lang="uz", **kw):
        self.lang = lang
        super().__init__(*a, **kw)
        for name, f in self.fields.items():
            if f.label:
                f.label = translate(str(f.label), lang)
            if f.help_text:
                f.help_text = translate(str(f.help_text), lang)
            if hasattr(f, "choices") and not hasattr(f, "queryset"):
                f.choices = [(v, _tr_label(l, lang)) for v, l in f.choices]
            w = f.widget
            if isinstance(w, forms.CheckboxSelectMultiple):
                continue
            if isinstance(w, forms.CheckboxInput):
                w.attrs.setdefault("class", "form-check-input")
            elif isinstance(w, forms.Select):
                w.attrs.setdefault("class", "form-select")
            else:
                w.attrs.setdefault("class", "form-control")
            if isinstance(w, forms.Textarea):
                w.attrs["rows"] = 2


DATE = forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")


def check_ranges(form, d, kind):
    """Fiziologik jihatdan mumkin bo'lmagan qiymatlar saqlanmaydi (ovoz/AI xatosi yoki qo'lda xato)."""
    from apps.voice.validate import CHILD_RANGES, MOTHER_RANGES
    for k, (lo, hi) in (MOTHER_RANGES if kind == "mother" else CHILD_RANGES).items():
        v = d.get(k)
        if v is not None and not lo <= float(v) <= hi:
            form.add_error(k, f"{translate('Mantiqsiz qiymat, tekshiring', form.lang)}: {v} ({lo}–{hi})")


class PatientForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = Patient
        fields = ["last_name", "first_name", "middle_name", "birth_date", "phone", "address", "mavze",
                  "lmp_date", "gravidity", "parity", "blood_group", "chronic_conditions", "previous_complications",
                  "consent"]
        widgets = {"birth_date": DATE, "lmp_date": DATE}
        labels = {"phone": "Telefon (Telegram bot uchun)"}
        help_texts = {"phone": "Ona faqat shu raqam bilan botga ulanib, o'z va farzandlari ma'lumotini ko'radi"}

    def __init__(self, *a, clinic=None, **kw):
        super().__init__(*a, **kw)
        if clinic:
            self.fields["mavze"].queryset = Mavze.objects.filter(clinic=clinic)
        if not self.instance.pk:  # yangi bemor: rozilik majburiy
            self.fields["consent"].required = True

    def clean_phone(self):
        p = "".join(ch for ch in self.cleaned_data["phone"] if ch.isdigit())
        if len(p) == 9:
            p = "998" + p
        if len(p) != 12 or not p.startswith("998"):
            raise forms.ValidationError(translate("Format: +998XXXXXXXXX", self.lang))
        return "+" + p


OVERRIDE_CHOICES = [("auto", "Tizim hisoblaganini tasdiqlayman")] + [
    (c, f"O'zgartirish: {l}") for c, l in COLOR_CHOICES]


class VisitForm(BootstrapMixin, forms.ModelForm):
    color_choice = forms.ChoiceField(label="Zona", choices=OVERRIDE_CHOICES, initial="auto")
    source = forms.CharField(widget=forms.HiddenInput, required=False)
    transcript = forms.CharField(widget=forms.HiddenInput, required=False)
    ai_fields = forms.CharField(widget=forms.HiddenInput, required=False)

    class Meta:
        model = Visit
        fields = ["visit_date", "gestational_week", "bp_sys", "bp_dia", "hb", "urine_protein", "fetal_movement",
                  "fetal_heart_rate", "weight", "temperature", "edema", "bleeding", "headache_vision",
                  "complaints", "complications", "diagnosis", "recommendation", "next_visit_date",
                  "color_override_note"]
        widgets = {"visit_date": DATE, "next_visit_date": DATE}

    def clean(self):
        d = super().clean()
        if d.get("color_choice") not in (None, "auto") and not d.get("color_override_note"):
            self.add_error("color_override_note", translate("Zonani o'zgartirsangiz, sababini yozing", self.lang))
        check_ranges(self, d, "mother")
        if d.get("bp_sys") and d.get("bp_dia") and d["bp_dia"] >= d["bp_sys"]:
            self.add_error("bp_dia", translate("Diastolik bosim sistolikdan kichik bo'lishi kerak", self.lang))
        return d
