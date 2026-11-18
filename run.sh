#!/usr/bin/env bash
# Hammasini bitta buyruqda ishga tushirish: web + scheduler (+ bot, agar token bo'lsa)
set -e
cd "$(dirname "$0")"
PY=.venv/bin/python
PORT=${PORT:-8000}

$PY manage.py migrate --noinput -v0
if [ "$($PY manage.py shell -c 'from apps.geo.models import District; print(District.objects.exists())')" != "True" ]; then
  echo "Demo ma'lumot yaratilmoqda..."; $PY manage.py seed_demo
fi

pids=()
cleanup() { kill "${pids[@]}" 2>/dev/null || true; }
trap cleanup EXIT INT TERM

$PY manage.py run_scheduler --interval 30 & pids+=($!)
if grep -qE '^TELEGRAM_BOT_TOKEN=.+' .env 2>/dev/null; then
  $PY manage.py run_bot & pids+=($!)
else
  echo "TELEGRAM_BOT_TOKEN yo'q — bot ishga tushirilmadi (xabarlar 'Telegram' sahifasida ko'rinadi)"
fi
echo "Sayt: http://localhost:$PORT  (loginlar: ovabmu | tuman_chilonzor | poliklinika_demo — parollar .env dagi PASS_* da)"
$PY manage.py runserver 0.0.0.0:$PORT --insecure   # --insecure: DEBUG=0 da ham statik fayllar
