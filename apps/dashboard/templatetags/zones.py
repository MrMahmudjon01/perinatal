from django import template
from django.utils.html import format_html

from apps.accounts.i18n import translate

register = template.Library()

LABEL = {"green": "Yashil", "yellow": "Sariq", "red": "Qizil", "none": "Ma'lumot yo'q"}
ICON = {"green": "bi-check-circle-fill", "yellow": "bi-exclamation-triangle-fill",
        "red": "bi-exclamation-octagon-fill", "none": "bi-dash-circle"}


@register.filter
def zone_label(color):
    return LABEL.get(color, color)


@register.filter
def zone_icon(color):
    return ICON.get(color, "bi-circle")


@register.simple_tag(takes_context=True)
def zone(context, color, small=False):
    """Zona belgisi: rang + ikonka + matn (rangning o'zi yagona belgi emas)."""
    lang = getattr(context.get("request"), "lang", "uz")
    return format_html('<span class="zone zone-{}{}"><i class="bi {}"></i> {}</span>', color,
                       " zone-sm" if small else "", ICON.get(color, "bi-circle"), translate(LABEL.get(color, color), lang))


@register.filter
def get(d, key):
    return d.get(key) if d else None


@register.filter
def days_ago(d):
    from datetime import date
    return (date.today() - d).days if d else ""
