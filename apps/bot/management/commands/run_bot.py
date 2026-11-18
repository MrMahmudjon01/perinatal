import asyncio
import logging
import os

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Telegram botni ishga tushiradi (long polling)"

    def handle(self, *args, **kw):
        os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "false")
        logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)s %(message)s")
        from apps.bot.bot import main
        asyncio.run(main())
