"""Xodimlar: profil yaratish, tahrirlash, bloklash va parolni tiklash — ierarxiya bo'yicha.

- OvaBMU   → tuman shifokorlari va OvaBMU mutaxassislarini boshqaradi; shahardagi barcha xodimlarni ko'radi.
- Tuman    → faqat o'z tumanidagi poliklinika xodimlarini boshqaradi.
- Poliklinika xodimi bu sahifani ko'rmaydi.
Parol tizim tomonidan yaratiladi va faqat bir marta ekranda ko'rsatiladi (bazada faqat xeshi saqlanadi).
"""
import secrets
import string

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.geo.models import Clinic, District

from . import scope
from .i18n import translate
from .models import User

ALPHABET = string.ascii_letters + string.digits


def gen_password(n=12):
    while True:
        p = "".join(secrets.choice(ALPHABET) for _ in range(n))
        if any(c.isdigit() for c in p) and any(c.isupper() for c in p) and any(c.islower() for c in p):
            return p


def creatable_roles(actor):
    if actor.role == User.OVABMU:
        return [User.DISTRICT, User.OVABMU]
    if actor.role == User.DISTRICT:
        return [User.CLINIC]
    return []


def visible_staff(actor):
    qs = User.objects.filter(is_superuser=False).select_related("clinic__district", "district")
    if actor.role == User.OVABMU:
        return qs
    if actor.role == User.DISTRICT:
        return qs.filter(Q(role=User.CLINIC, clinic__district=actor.district) | Q(pk=actor.pk))
    return qs.none()


def can_manage(actor, target):
    if target.is_superuser or target.pk == actor.pk:
        return False
    if actor.role == User.OVABMU:
        return target.role in (User.DISTRICT, User.OVABMU)
    if actor.role == User.DISTRICT:
        return target.role == User.CLINIC and target.clinic and target.clinic.district_id == actor.district_id
    return False


class StaffForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["username", "full_name", "position", "phone", "role", "district", "clinic", "clinic_role", "mavze"]

    def __init__(self, *a, actor=None, lang="uz", **kw):
        super().__init__(*a, **kw)
        self.actor = actor
        roles = creatable_roles(actor)
        f = self.fields
        f["role"].choices = [(k, translate(l, lang)) for k, l in User.ROLE_CHOICES if k in roles]
        f["full_name"].required = True
        f["username"].label = "Login"
        f["district"].queryset = District.objects.order_by("name")
        f["clinic"].queryset = Clinic.objects.select_related("district").order_by("district__name", "number")
        from apps.geo.models import Mavze
        f["mavze"].queryset = Mavze.objects.select_related("clinic").order_by("clinic__number", "name")
        f["mavze"].label_from_instance = lambda m: f"{m.clinic.name} — {m.name}"
        f["clinic_role"].choices = [(k, translate(l, lang)) for k, l in User.CLINIC_ROLE_CHOICES]
        if actor.role == User.DISTRICT:
            f["mavze"].queryset = f["mavze"].queryset.filter(clinic__district=actor.district)
            f["clinic"].queryset = f["clinic"].queryset.filter(district=actor.district)
            f["clinic"].label_from_instance = lambda c: c.name
            del f["district"]
        if self.instance.pk:
            f["username"].disabled = True
            f["role"].disabled = True
        for name, fld in f.items():
            if fld.label:
                fld.label = translate(str(fld.label), lang)
            fld.help_text = ""
            fld.widget.attrs.setdefault("class", "form-select" if isinstance(fld.widget, forms.Select) else "form-control")

    def clean(self):
        d = super().clean()
        role = d.get("role") or self.instance.role
        if role not in creatable_roles(self.actor) and not self.instance.pk:
            raise forms.ValidationError("Bu rolni yaratishga ruxsatingiz yo'q")
        if role == User.CLINIC:
            if not d.get("clinic"):
                self.add_error("clinic", "Poliklinikani tanlang")
            d["district"] = d["clinic"].district if d.get("clinic") else None
            if d.get("mavze") and d.get("clinic") and d["mavze"].clinic_id != d["clinic"].id:
                self.add_error("mavze", "Mavze shu poliklinikaga tegishli emas")
            if d.get("clinic_role") != User.NURSE:
                d["mavze"] = None
        elif role == User.DISTRICT:
            if not d.get("district"):
                self.add_error("district", "Tumanni tanlang")
            d["clinic"] = None
        else:
            d["district"], d["clinic"] = None, None
        if role != User.CLINIC:
            d["clinic_role"], d["mavze"] = User.FAMILY, None
        return d

    def save(self, commit=True):
        u = super().save(commit=False)
        u.district, u.clinic = self.cleaned_data.get("district"), self.cleaned_data.get("clinic")
        u.clinic_role, u.mavze = self.cleaned_data.get("clinic_role") or User.FAMILY, self.cleaned_data.get("mavze")
        if commit:
            u.save()
        return u


def _require_manager(user):
    scope.require(user.role in (User.OVABMU, User.DISTRICT))


@login_required
def staff_list(request):
    u = request.user
    _require_manager(u)
    qs = visible_staff(u)
    role, status, q = request.GET.get("role", ""), request.GET.get("status", ""), request.GET.get("q", "").strip()
    district = request.GET.get("district", "")
    if role:
        qs = qs.filter(role=role)
    if status == "active":
        qs = qs.filter(is_active=True)
    elif status == "blocked":
        qs = qs.filter(is_active=False)
    if district.isdigit():
        qs = qs.filter(Q(district_id=district) | Q(clinic__district_id=district))
    for w in q.split():
        qs = qs.filter(Q(full_name__icontains=w) | Q(username__icontains=w) | Q(phone__icontains=w) |
                       Q(clinic__name__icontains=w))
    base = visible_staff(u)
    kpi = {"total": base.count(), "active": base.filter(is_active=True).count(),
           "blocked": base.filter(is_active=False).count(),
           "never": base.filter(last_login__isnull=True, is_active=True).count()}
    qs = qs.order_by("role", "district__name", "clinic__district__name", "clinic__number", "full_name")
    page = Paginator(qs, 25).get_page(request.GET.get("page"))
    for s in page:
        s.manageable = can_manage(u, s)
        s.has_pw = s.has_usable_password()
    params = request.GET.copy()
    params.pop("page", None)
    return render(request, "accounts/staff_list.html", {
        "page": page, "kpi": kpi, "role": role, "status": status, "q": q, "district": district,
        "roles": [(k, l) for k, l in User.ROLE_CHOICES if u.role == User.OVABMU or k == User.CLINIC],
        "districts": District.objects.order_by("name") if u.role == User.OVABMU else [],
        "can_create": bool(creatable_roles(u)), "qs_nopage": params.urlencode(),
        "creds": request.session.pop("staff_creds", None),
    })


def _show_creds(request, user, password, action):
    """Parol faqat bir marta ko'rsatiladi: sessiyaga qo'yiladi va keyingi sahifa ochilishida o'chiriladi."""
    request.session["staff_creds"] = {"username": user.username, "password": password,
                                      "name": user.full_name, "action": action}


@login_required
def staff_create(request):
    u = request.user
    _require_manager(u)
    lang = getattr(request, "lang", "uz")
    form = StaffForm(request.POST or None, actor=u, lang=lang)
    if request.method == "POST" and form.is_valid():
        s = form.save(commit=False)
        pw = gen_password()
        s.set_password(pw)
        s.save()
        _show_creds(request, s, pw, "created")
        return redirect("staff_list")
    return render(request, "accounts/staff_form.html", {"form": form, "obj": None})


@login_required
def staff_edit(request, pk):
    u = request.user
    _require_manager(u)
    s = get_object_or_404(User, pk=pk)
    scope.require(can_manage(u, s))
    form = StaffForm(request.POST or None, instance=s, actor=u, lang=getattr(request, "lang", "uz"))
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, f"{s.full_name}: ma'lumotlar saqlandi")
        return redirect("staff_list")
    return render(request, "accounts/staff_form.html", {"form": form, "obj": s})


@login_required
@require_POST
def staff_toggle(request, pk):
    u = request.user
    _require_manager(u)
    s = get_object_or_404(User, pk=pk)
    scope.require(can_manage(u, s))
    s.is_active = not s.is_active
    s.save(update_fields=["is_active"])
    messages.success(request, f"{s.full_name}: {'faollashtirildi' if s.is_active else 'bloklandi — tizimga kira olmaydi'}")
    return redirect(request.POST.get("next") or "staff_list")


@login_required
@require_POST
def staff_reset(request, pk):
    u = request.user
    _require_manager(u)
    s = get_object_or_404(User, pk=pk)
    scope.require(can_manage(u, s))
    pw = gen_password()
    s.set_password(pw)
    s.save(update_fields=["password"])
    _show_creds(request, s, pw, "reset")
    return redirect(request.POST.get("next") or "staff_list")
