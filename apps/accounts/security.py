"""Internetga ochiq sayt uchun himoya: login urinishlarini cheklash, tez kirish faqat lokalda, qidiruv tizimlariga yopiq."""
from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse


def client_ip(request):
    fwd = request.META.get("HTTP_X_FORWARDED_FOR", "")
    return fwd.split(",")[0].strip() if fwd else request.META.get("REMOTE_ADDR", "")


def is_local(request):
    host = request.get_host().split(":")[0]
    return host in settings.QUICK_LOGIN_HOSTS and not request.META.get("HTTP_X_FORWARDED_FOR")


def _keys(request, username):
    ip = client_ip(request)
    return f"login-fail:ip:{ip}", f"login-fail:user:{(username or '').lower()}"


def locked(request, username):
    return any(cache.get(k, 0) >= settings.LOGIN_MAX_FAILS for k in _keys(request, username))


def register_fail(request, username):
    for k in _keys(request, username):
        try:
            cache.incr(k)
        except ValueError:
            cache.set(k, 1, settings.LOGIN_LOCK_MINUTES * 60)


def reset_fails(request, username):
    cache.delete_many(list(_keys(request, username)))


def robots_txt(request):
    return HttpResponse("User-agent: *\nDisallow: /\n", content_type="text/plain")


class NoIndexMiddleware:
    """Qidiruv tizimlari sahifalarni indekslamasin."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response["X-Robots-Tag"] = "noindex, nofollow, noarchive"
        return response
