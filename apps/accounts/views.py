from django.contrib import messages
from django.contrib.auth import authenticate, login
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from .models import User



def login_view(request):
    from . import security
    from .i18n import tr
    local = security.is_local(request)
    if request.method == "POST":
        username = request.POST.get("username", "")
        if request.POST.get("quick") and local:
            # Tez kirish — faqat shu kompyuterdan (localhost), tashqi manzildan ishlamaydi
            user = User.objects.filter(username=username, is_active=True).exclude(is_superuser=True).first()
        elif security.locked(request, username):
            messages.error(request, tr(request, "Ko'p marta noto'g'ri urinish. 15 daqiqadan keyin qayta urinib ko'ring."))
            return redirect("login")
        else:
            user = authenticate(request, username=username, password=request.POST.get("password"))
            if user is None:
                security.register_fail(request, username)
        if user:
            security.reset_fails(request, username)
            login(request, user, backend="django.contrib.auth.backends.ModelBackend")
            return redirect(request.GET.get("next") or "home")
        messages.error(request, tr(request, "Login yoki parol noto'g'ri"))
    demo_list = []
    if local:
        demo = {
            "ovabmu": User.objects.filter(username="ovabmu").first(),
            "district": User.objects.filter(username="tuman_chilonzor").first(),
            "clinic": User.objects.filter(username="poliklinika_demo").first(),
        }
        demo_list = [(demo["clinic"], "bi-hospital", "Poliklinika shifokori"),
                     (demo["district"], "bi-buildings", "Tuman/shahar shifokori"),
                     (demo["ovabmu"], "bi-shield-plus", "OvaBMU mutaxassisi")]
    return render(request, "accounts/login.html", {"demo_list": [d for d in demo_list if d[0]]})


@login_required
def profile(request):
    return render(request, "accounts/profile.html")




def set_lang(request, code):
    from django.shortcuts import redirect as _r
    from django.utils.http import url_has_allowed_host_and_scheme

    from .i18n import LANGS
    nxt = request.GET.get("next") or "/"
    if not url_has_allowed_host_and_scheme(nxt, allowed_hosts={request.get_host()}):
        nxt = "/"
    resp = _r(nxt)
    if code in [c for c, _, _ in LANGS]:
        resp.set_cookie("lang", code, max_age=365 * 24 * 3600, samesite="Lax")
    return resp


@login_required
def set_view_district(request, pk):
    """OvaBMU: 0 — butun shahar, aks holda bitta tuman."""
    from django.utils.http import url_has_allowed_host_and_scheme

    from apps.geo.models import District
    if request.user.role == User.OVABMU:
        if pk and District.objects.filter(pk=pk).exists():
            request.session["view_district"] = pk
        else:
            request.session.pop("view_district", None)
        request.session.pop("view_clinic", None)
    nxt = request.GET.get("next") or "/"
    if not url_has_allowed_host_and_scheme(nxt, allowed_hosts={request.get_host()}) or "/regions/district/" in nxt:
        nxt = "/"
    return redirect(nxt)


@login_required
def set_view_clinic(request, pk):
    """OvaBMU / tuman: 0 — barcha poliklinikalar, aks holda bitta poliklinika (o'z hududi doirasida)."""
    from django.utils.http import url_has_allowed_host_and_scheme

    from apps.geo.models import Clinic
    u = request.user
    if u.role in (User.OVABMU, User.DISTRICT):
        c = Clinic.objects.filter(pk=pk).first() if pk else None
        if c and (u.role == User.OVABMU or c.district_id == u.district_id):
            request.session["view_clinic"] = c.id
            if u.role == User.OVABMU:
                request.session["view_district"] = c.district_id
        else:
            request.session.pop("view_clinic", None)
    nxt = request.GET.get("next") or "/"
    if not url_has_allowed_host_and_scheme(nxt, allowed_hosts={request.get_host()}):
        nxt = "/"
    return redirect(nxt)
