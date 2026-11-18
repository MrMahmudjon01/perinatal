"""Perinatal yuqori xavf guruhi registri — Django sozlamalari."""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def env(key, default=None):
    return os.environ.get(key, default)


SECRET_KEY = env("SECRET_KEY", "dev-insecure-change-me")
DEBUG = env("DEBUG", "1") == "1"
ALLOWED_HOSTS = env("ALLOWED_HOSTS", "*").split(",")
CSRF_TRUSTED_ORIGINS = [o for o in env("CSRF_TRUSTED_ORIGINS", "").split(",") if o]
# Reverse proxy (nginx) orqasida: HTTPS ni to'g'ri aniqlash
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "apps.accounts",
    "apps.geo",
    "apps.patients",
    "apps.children",
    "apps.alerts",
    "apps.risk",
    "apps.voice",
    "apps.dashboard",
    "apps.bot",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "apps.accounts.i18n.LanguageMiddleware",
    "apps.accounts.i18n.DistrictViewMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.accounts.security.NoIndexMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "builtins": ["apps.accounts.templatetags.i18n_t"],
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.accounts.context.role_context",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("DB_NAME", "perinatal"),
        "USER": env("DB_USER", "perinatal"),
        "PASSWORD": env("DB_PASSWORD", ""),
        "HOST": env("DB_HOST", "localhost"),
        "PORT": env("DB_PORT", "5432"),
        "CONN_MAX_AGE": 60,  # ulanishni qayta ishlatish: har so'rovda yangi ulanish ochilmaydi
        "CONN_HEALTH_CHECKS": True,
    }
}

AUTH_USER_MODEL = "accounts.User"
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "home"
LOGOUT_REDIRECT_URL = "login"

AUTH_PASSWORD_VALIDATORS = []

LANGUAGE_CODE = "uz"
TIME_ZONE = "Asia/Tashkent"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Loyiha sozlamalari ---
RULES_FILE = BASE_DIR / "rules.json"

TELEGRAM_BOT_TOKEN = env("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_BOT_USERNAME = env("TELEGRAM_BOT_USERNAME", "")

VOICE_MODE = env("VOICE_MODE", "mock")  # mock | voicelab
VOICELAB_API_KEY = env("VOICELAB_API_KEY", "")
VOICELAB_BASE_URL = env("VOICELAB_BASE_URL", "https://api.voicelab.uz")
VOICELAB_LLM_MODEL = env("VOICELAB_LLM_MODEL", "aisha-orbit")

# Signal javobsiz qolsa, necha daqiqadan keyin yuqori bosqichga ko'tariladi
ALERT_ESCALATION_MINUTES = int(env("ALERT_ESCALATION_MINUTES", "30"))

# --- Xavfsizlik (internetga ochiq bo'lganda)
DEMO_PASSWORDS = {
    "ovabmu": env("PASS_OVABMU", ""),
    "tuman_chilonzor": env("PASS_TUMAN", ""),
    "poliklinika_demo": env("PASS_POLIKLINIKA", ""),
    "ginekolog_demo": env("PASS_POLIKLINIKA", ""),
    "pediatr_demo": env("PASS_POLIKLINIKA", ""),
    "hamshira_demo": env("PASS_POLIKLINIKA", ""),
    "admin": env("PASS_ADMIN", ""),
}
LOGIN_MAX_FAILS = 5          # shuncha xato urinishdan keyin
LOGIN_LOCK_MINUTES = 15      # shuncha daqiqaga bloklanadi
QUICK_LOGIN_HOSTS = ("localhost", "127.0.0.1")   # tez kirish tugmalari faqat shu manzillarda
