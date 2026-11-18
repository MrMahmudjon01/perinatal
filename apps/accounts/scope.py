"""Rolga qarab ma'lumotni filtrlash: bitta baza, har rolga o'z ko'rinishi."""
from django.core.exceptions import PermissionDenied

from .models import User


def view_district_id(user):
    """OvaBMU yuqoridagi tanlagichda bitta tumanni tanlagan bo'lsa — uning ID si, aks holda None (butun shahar)."""
    return getattr(user, "view_district_id", None) if user.role == User.OVABMU else None


def view_clinic_id(user):
    """OvaBMU yoki tuman yuqoridagi tanlagichda bitta poliklinikani tanlagan bo'lsa — uning ID si."""
    return getattr(user, "view_clinic_id", None) if user.role in (User.OVABMU, User.DISTRICT) else None


def patients_for(user, qs):
    if user.role == User.CLINIC:
        if user.clinic_role == User.NURSE and user.mavze_id:  # patronaj hamshira — faqat o'z mavzesi
            return qs.filter(mavze_id=user.mavze_id)
        return qs.filter(mavze__clinic=user.clinic)
    if vc := view_clinic_id(user):
        qs = qs.filter(mavze__clinic_id=vc)
    if user.role == User.DISTRICT:
        return qs.filter(mavze__clinic__district=user.district)
    if vd := view_district_id(user):
        return qs.filter(mavze__clinic__district_id=vd)
    return qs


def children_for(user, qs):
    if user.role == User.CLINIC:
        if user.clinic_role == User.NURSE and user.mavze_id:
            return qs.filter(mother__mavze_id=user.mavze_id)
        return qs.filter(mother__mavze__clinic=user.clinic)
    if vc := view_clinic_id(user):
        qs = qs.filter(mother__mavze__clinic_id=vc)
    if user.role == User.DISTRICT:
        return qs.filter(mother__mavze__clinic__district=user.district)
    if vd := view_district_id(user):
        return qs.filter(mother__mavze__clinic__district_id=vd)
    return qs


def alerts_for(user, qs):
    """Poliklinika — o'z poliklinikasi signallari; tuman — o'z tumani; OvaBMU — OvaBMU darajasidagilar."""
    if user.role == User.CLINIC:
        return qs.filter(clinic=user.clinic)
    if vc := view_clinic_id(user):
        qs = qs.filter(clinic_id=vc)
    if user.role == User.DISTRICT:
        return qs.filter(district=user.district)
    if vd := view_district_id(user):
        return qs.filter(level="ovabmu", district_id=vd)
    return qs.filter(level="ovabmu")


def referrals_for(user, qs):
    if user.role == User.CLINIC:
        return qs.filter(clinic=user.clinic)
    if vc := view_clinic_id(user):
        qs = qs.filter(clinic_id=vc)
    if user.role == User.DISTRICT:
        return qs.filter(district=user.district)
    if vd := view_district_id(user):
        return qs.filter(to_level="ovabmu", district_id=vd)
    return qs.filter(to_level="ovabmu")


def can_see_clinic(user, clinic):
    if user.role == User.CLINIC:
        return user.clinic_id == clinic.id
    if user.role == User.DISTRICT:
        return user.district_id == clinic.district_id
    return True


def can_see_district(user, district):
    if user.role == User.CLINIC:
        return False
    if user.role == User.DISTRICT:
        return user.district_id == district.id
    return True


def require(cond):
    if not cond:
        raise PermissionDenied("Bu ma'lumot sizning hududingizga tegishli emas")


def _own(user, clinic):
    return user.role == User.CLINIC and clinic is not None and user.clinic_id == clinic.id


def can_edit_clinical(user, clinic):
    """Homilador: ro'yxatga olish, profil, ko'rik — oilaviy shifokor va akusher-ginekolog (o'z poliklinikasi)."""
    return _own(user, clinic) and user.clinic_role in (User.FAMILY, User.GYN, "")


can_edit_mother = can_edit_clinical


def can_edit_child(user, clinic):
    """Bola: ro'yxatga olish, ko'rik — oilaviy shifokor va pediatr."""
    return _own(user, clinic) and user.clinic_role in (User.FAMILY, User.PED, "")


def can_vaccinate(user, clinic):
    """Emlashni belgilash va emlash e'loni — oilaviy shifokor, pediatr, patronaj hamshira."""
    return _own(user, clinic) and user.clinic_role in (User.FAMILY, User.PED, User.NURSE, "")


def can_resolve_alert(user, alert):
    """Signal bo'yicha chora: poliklinikada — ona signali ginekolog/oilaviy, bola signali pediatr/oilaviy."""
    if user.role != User.CLINIC:
        return True
    if alert.clinic_id != user.clinic_id:
        return False
    if alert.child_id:
        return user.clinic_role in (User.FAMILY, User.PED, "")
    return user.clinic_role in (User.FAMILY, User.GYN, "")


def can_refer(user):
    return user.role != User.CLINIC or user.clinic_role != User.NURSE


def nav_for(user):
    """Menyuda nima ko'rinadi — keraksiz bo'limlar yashiriladi."""
    r, cr = user.role, getattr(user, "clinic_role", "")
    nurse, gyn = r == User.CLINIC and cr == User.NURSE, r == User.CLINIC and cr == User.GYN
    return {
        "map": r != User.CLINIC, "regions": not nurse, "staff": r != User.CLINIC, "dynamics": r != User.CLINIC,
        "vaccination": not gyn, "sessions": r == User.CLINIC and not gyn,
        "patronage": r != User.OVABMU, "referrals": not nurse, "stats": not nurse,
        "telegram": True,
    }
