"""Telegram'ga xabar yuborish (Django jarayonidan). Har bir xabar Notification jadvaliga yoziladi.

Bot token bo'lmasa ham xabar logga tushadi — demo vaqtida "Telegram xabarlar" sahifasida ko'rinadi.
"""
import logging

import requests
from django.conf import settings

from apps.alerts.models import Notification

log = logging.getLogger(__name__)
MAX_LEN = 4000


def split_text(text, limit=MAX_LEN):
    parts, buf = [], ""
    for line in text.split("\n"):
        if len(buf) + len(line) + 1 > limit:
            parts.append(buf)
            buf = ""
        buf += line + "\n"
    if buf.strip():
        parts.append(buf)
    return parts


def send(chat_id, text, *, kind, recipient_label, buttons=None, patient=None):
    """buttons: [[(matn, callback_data | url), ...], ...]"""
    n = Notification(chat_id=chat_id, text=text, kind=kind, recipient_label=recipient_label, patient=patient)
    token = settings.TELEGRAM_BOT_TOKEN
    if not chat_id:
        n.status = Notification.NO_CHAT
    elif not token:
        n.status = Notification.NO_TOKEN
    else:
        try:
            chunks = split_text(text)
            for i, chunk in enumerate(chunks):
                payload = {"chat_id": chat_id, "text": chunk, "parse_mode": "HTML",
                           "disable_web_page_preview": True}
                if buttons and i == len(chunks) - 1:
                    payload["reply_markup"] = {"inline_keyboard": [
                        [({"text": t, "url": d} if d.startswith("http") else {"text": t, "callback_data": d})
                         for t, d in row] for row in buttons]}
                r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage", json=payload, timeout=10)
                if not r.ok:
                    raise RuntimeError(r.json().get("description", r.text)[:200])
            n.status = Notification.SENT
        except Exception as e:  # tarmoq xatosi signal yaratilishini to'xtatmasligi kerak
            log.warning("Telegram xato: %s", e)
            n.status = Notification.FAILED
            n.error = str(e)[:255]
    n.save()
    return n
