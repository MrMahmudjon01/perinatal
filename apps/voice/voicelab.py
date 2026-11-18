"""VoiceLab API mijozi: https://docs.voicelab.uz/

STT: POST /v1/stt (multipart, async) → GET /v1/stt/transcriptions/{id} (polling) → DELETE (audio o'chiriladi)
LLM: POST /v1/chat/completions — tuzilgan javob function calling (tools) orqali olinadi.
"""
import json
import time
import uuid

import requests
from django.conf import settings


class VoiceLabError(Exception):
    pass


def _headers(**extra):
    if not settings.VOICELAB_API_KEY:
        raise VoiceLabError("VOICELAB_API_KEY sozlanmagan")
    return {"Authorization": f"Bearer {settings.VOICELAB_API_KEY}", **extra}


def _url(path):
    return settings.VOICELAB_BASE_URL.rstrip("/") + path


def _err(r):
    try:
        e = r.json().get("error", {})
        return f"{r.status_code} {e.get('code', '')}: {e.get('message', r.text[:200])}"
    except ValueError:
        return f"{r.status_code}: {r.text[:200]}"


def transcribe(audio_bytes, filename="audio.webm", content_type="audio/webm", language="uz", timeout=90):
    r = requests.post(
        _url("/v1/stt"),
        headers=_headers(**{"Idempotency-Key": str(uuid.uuid4())}),
        files={"audio": (filename, audio_bytes, content_type)},
        data={"language": language, "include_speakers": "false"},
        timeout=60,
    )
    if r.status_code not in (200, 202):
        raise VoiceLabError("STT yuborishda xato: " + _err(r))
    job_id = r.json()["id"]
    deadline = time.monotonic() + timeout
    try:
        while time.monotonic() < deadline:
            p = requests.get(_url(f"/v1/stt/transcriptions/{job_id}"), headers=_headers(), timeout=20)
            if not p.ok:
                raise VoiceLabError("STT holatini olishda xato: " + _err(p))
            data = p.json()
            if data["status"] == "completed":
                return data.get("transcript", ""), data
            if data["status"] == "failed":
                raise VoiceLabError("STT bajarilmadi")
            time.sleep(float(p.headers.get("Retry-After", 1)))
        raise VoiceLabError("STT vaqt chegarasidan oshdi")
    finally:
        # Xavfsizlik qoidasi: audio matnga o'tgach o'chiriladi
        try:
            requests.delete(_url(f"/v1/stt/transcriptions/{job_id}"), headers=_headers(), timeout=10)
        except requests.RequestException:
            pass


def chat_tool(system, user, tool_name, tool_description, parameters, model=None, timeout=60):
    """LLM'dan JSON-schema bo'yicha tuzilgan javob oladi (function calling)."""
    body = {
        "model": model or settings.VOICELAB_LLM_MODEL,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "tools": [{"type": "function", "function": {"name": tool_name, "description": tool_description,
                                                     "parameters": parameters}}],
        "tool_choice": {"type": "function", "function": {"name": tool_name}},
        "temperature": 0,
        "max_tokens": 4000,
        "reasoning_effort": "low",  # tuzilgan javob uchun chuqur "o'ylash" kerak emas — tezroq va token tejaladi
    }
    r = requests.post(_url("/v1/chat/completions"),
                      headers=_headers(**{"Content-Type": "application/json", "Idempotency-Key": str(uuid.uuid4())}),
                      json=body, timeout=timeout)
    if not r.ok:
        raise VoiceLabError("LLM xatosi: " + _err(r))
    msg = r.json()["choices"][0]["message"]
    for call in msg.get("tool_calls") or []:
        if call.get("function", {}).get("name") == tool_name:
            args = call["function"]["arguments"]
            try:
                return json.loads(args) if isinstance(args, str) else args
            except ValueError as e:
                raise VoiceLabError("LLM javobi to'liq kelmadi") from e
    content = (msg.get("content") or "").strip()
    if content.startswith("```"):
        content = content.strip("`").removeprefix("json").strip()
    try:
        return json.loads(content)
    except ValueError as e:
        raise VoiceLabError("LLM tuzilgan javob qaytarmadi") from e


def chat(messages, model=None, max_tokens=1500, timeout=45):
    """Oddiy suhbat javobi (matn). messages: [{"role": "system"|"user"|"assistant", "content": ...}]."""
    body = {"model": model or settings.VOICELAB_LLM_MODEL, "messages": messages, "temperature": 0.3,
            "max_tokens": max_tokens, "reasoning_effort": "low"}
    r = requests.post(_url("/v1/chat/completions"),
                      headers=_headers(**{"Content-Type": "application/json", "Idempotency-Key": str(uuid.uuid4())}),
                      json=body, timeout=timeout)
    if not r.ok:
        raise VoiceLabError("LLM xatosi: " + _err(r))
    return (r.json()["choices"][0]["message"].get("content") or "").strip()
