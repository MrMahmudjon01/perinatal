from django import template

from apps.accounts.i18n import translate

register = template.Library()


@register.simple_tag(takes_context=True)
def t(context, text):
    req = context.get("request")
    return translate(text, getattr(req, "lang", "uz"))


@register.filter
def tl(text, lang):
    return translate(text, lang)
