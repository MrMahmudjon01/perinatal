from django.conf import settings

from . import scope as _scope
from .i18n import LANGS

NAV = {
    "home": "overview", "overview": "overview",
    "map_page": "map",
    "regions": "regions", "district_dashboard": "regions", "clinic_dashboard": "regions",
    "patient_list": "patients", "patient_detail": "patients", "patient_create": "patients", "patient_edit": "patients",
    "visit_create": "patients",
    "child_list": "children", "child_detail": "children", "child_create": "children", "child_visit_create": "children",
    "vaccination_page": "vaccination", "patronage_page": "patronage",
    "session_list": "sessions", "session_create": "sessions", "session_detail": "sessions",
    "alert_list": "alerts", "referral_list": "referrals", "stats_page": "stats", "dynamics_page": "dynamics", "project_page": "project", "staff_list": "staff", "staff_create": "staff", "staff_edit": "staff",
    "notification_log": "telegram", "about": "about", "profile": "profile",
}


def role_context(request):
    u = getattr(request, "user", None)
    if not u or not u.is_authenticated:
        return {"langs": LANGS, "lang": getattr(request, "lang", "uz")}
    name = request.resolver_match.url_name if request.resolver_match else ""
    view_district = None
    districts = []
    if u.role == "ovabmu":
        from apps.geo.models import District
        districts = list(District.objects.order_by("name").values("id", "name"))
        vd = getattr(u, "view_district_id", None)
        view_district = next((d for d in districts if d["id"] == vd), None)
    clinics, view_clinic = [], None
    if u.role in ("ovabmu", "district"):
        from apps.geo.models import Clinic
        did = u.district_id if u.role == "district" else getattr(u, "view_district_id", None)
        if did:
            clinics = list(Clinic.objects.filter(district_id=did).order_by("number", "name").values("id", "name"))
            vc = getattr(u, "view_clinic_id", None)
            view_clinic = next((c for c in clinics if c["id"] == vc), None)
    initials = "".join(w[0] for w in (u.full_name or u.username).split()[:2]).upper()
    return {
        "is_clinic": u.role == "clinic",
        "is_district": u.role == "district",
        "is_ovabmu": u.role == "ovabmu",
        "show": _scope.nav_for(u),
        "can_add_patient": _scope.can_edit_clinical(u, u.clinic) if u.role == "clinic" else False,
        "can_sessions": _scope.can_vaccinate(u, u.clinic) if u.role == "clinic" else False,
        "is_nurse": u.role == "clinic" and u.clinic_role == "nurse",
        "nav": NAV.get(name, ""),
        "all_districts": districts,
        "view_district": view_district,
        "scope_clinics": clinics,
        "view_clinic": view_clinic,
        "langs": LANGS,
        "lang": getattr(request, "lang", "uz"),
        "user_initials": initials,
        "voice_mode": settings.VOICE_MODE,
        "bot_username": settings.TELEGRAM_BOT_USERNAME,
    }
