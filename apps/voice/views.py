from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from . import service
from .voicelab import VoiceLabError


@require_POST
@login_required
def extract(request):
    """Audio (yoki tahrirlangan matn) → maydonlar. Hech narsa saqlanmaydi — faqat formani to'ldirish uchun."""
    kind = request.POST.get("kind", "mother")
    if kind not in ("mother", "child"):
        return JsonResponse({"error": "kind noto'g'ri"}, status=400)
    text = request.POST.get("text", "").strip()
    try:
        if not text:
            audio = request.FILES.get("audio")
            scenario = request.POST.get("scenario")
            if audio is None and settings.VOICE_MODE == "voicelab":
                if not scenario:
                    return JsonResponse({"error": "Audio yuborilmadi"}, status=400)
                # Mikrofonsiz demo: tayyor ko'rik matni haqiqiy LLM'ga yuboriladi (STT bosqichi o'tkazib yuboriladi)
                from . import mock
                text = mock.transcript(kind, scenario)
            else:
                text, _ = service.transcribe(audio, kind, scenario)
        result = service.extract(kind, text, getattr(request, "lang", "uz"))
    except VoiceLabError as e:
        return JsonResponse({"error": str(e)}, status=502)
    return JsonResponse({"transcript": text, "mode": settings.VOICE_MODE, **result})
