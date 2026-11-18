"""Telegram bot (aiogram 3). Ishga tushirish: python manage.py run_bot

Onalar: telefon raqamini ulashadi → registrdagi bemorga bog'lanadi → o'z va farzandlari ma'lumotini ko'radi.
Bot faqat onalar uchun. Shifokor va OvaBMU sayt orqali ishlaydi.
"""
import logging
import re

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import (CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, Message,
                           ReplyKeyboardMarkup, ReplyKeyboardRemove)
from asgiref.sync import sync_to_async
from django.conf import settings

from apps.accounts import scope
from apps.accounts.models import User
from apps.alerts import services
from apps.alerts.models import Alert
from apps.children.models import Child
from apps.patients.models import Patient

from . import sender, texts

log = logging.getLogger(__name__)
dp = Dispatcher()

BTN_ME, BTN_HISTORY, BTN_KIDS, BTN_UPCOMING, BTN_HELP = (
    "🤰 Mening ma'lumotlarim", "📋 Ko'riklarim tarixi", "👶 Farzandlarim", "📅 Qabul va emlashlar", "ℹ️ Yordam")
BTN_DANGER = "🚨 Xavf belgilari"
BTN_AI = "🤖 AI yordamchi"

MENU = ReplyKeyboardMarkup(resize_keyboard=True, keyboard=[
    [KeyboardButton(text=BTN_DANGER)],
    [KeyboardButton(text=BTN_ME), KeyboardButton(text=BTN_HISTORY)],
    [KeyboardButton(text=BTN_KIDS), KeyboardButton(text=BTN_UPCOMING)],
    [KeyboardButton(text=BTN_AI), KeyboardButton(text=BTN_HELP)],
])
ASK_PHONE = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True, keyboard=[
    [KeyboardButton(text="📱 Telefon raqamimni yuborish", request_contact=True)]])


# ---------- ORM yordamchilari ----------

@sync_to_async
def get_patient(chat_id):
    return Patient.objects.select_related("mavze__clinic").filter(telegram_chat_id=chat_id).first()


@sync_to_async
def link_patient(phone, chat_id):
    digits = re.sub(r"\D", "", phone)
    if len(digits) == 9:
        digits = "998" + digits
    p = Patient.objects.filter(phone="+" + digits).first()
    if not p:
        return None
    Patient.objects.filter(telegram_chat_id=chat_id).exclude(pk=p.pk).update(telegram_chat_id=None)
    p.telegram_chat_id = chat_id
    p.save(update_fields=["telegram_chat_id"])
    return p.first_name


@sync_to_async
def render(fn, *args):
    return fn(*args)


@sync_to_async
def mother_child(chat_id, child_id):
    return Child.objects.select_related("mother").filter(id=child_id, mother__telegram_chat_id=chat_id).first()


async def reply_long(message: Message, text, **kw):
    parts = sender.split_text(text)
    for i, part in enumerate(parts):
        await message.answer(part, **(kw if i == len(parts) - 1 else {}))


# ---------- Handlerlar ----------

@dp.message(CommandStart())
async def start(message: Message, command: CommandObject):
    p = await get_patient(message.chat.id)
    if p:
        await message.answer(f"Assalomu alaykum, {p.first_name}! Kerakli bo'limni tanlang 👇", reply_markup=MENU)
        return
    await message.answer(
        "Assalomu alaykum! 👋\nBu — <b>ona va bola salomatligi</b> boti.\n\nMa'lumotlaringizni ko'rish uchun "
        "poliklinikada ro'yxatdan o'tgan telefon raqamingizni yuboring 👇", reply_markup=ASK_PHONE)


@dp.message(F.contact)
async def contact(message: Message):
    c = message.contact
    if c.user_id != message.from_user.id:
        await message.answer("Iltimos, faqat o'zingizning raqamingizni yuboring.", reply_markup=ASK_PHONE)
        return
    name = await link_patient(c.phone_number, message.chat.id)
    if not name:
        await message.answer("Bu raqam registrda topilmadi. Oilaviy poliklinikangizga murojaat qiling — "
                             "shifokor raqamingizni kiritgach, qayta urinib ko'ring.", reply_markup=ASK_PHONE)
        return
    await message.answer(f"✅ Rahmat, {name}! Siz ulandingiz.\nQabul va emlash kunlari haqida oldindan "
                         f"eslatib turaman. Kerakli bo'limni tanlang 👇", reply_markup=MENU)


async def _require_patient(message):
    p = await get_patient(message.chat.id)
    if not p:
        await message.answer("Avval telefon raqamingizni yuboring 👇", reply_markup=ASK_PHONE)
    return p


@dp.message(F.text == BTN_ME)
async def me(message: Message):
    if p := await _require_patient(message):
        await reply_long(message, await render(texts.mother_profile, p))


@dp.message(F.text == BTN_HISTORY)
async def history(message: Message):
    if p := await _require_patient(message):
        await reply_long(message, await render(texts.mother_history, p))


@dp.message(F.text == BTN_UPCOMING)
async def upcoming(message: Message):
    if p := await _require_patient(message):
        await reply_long(message, await render(texts.upcoming, p))


@dp.message(F.text == BTN_KIDS)
async def kids(message: Message):
    if p := await _require_patient(message):
        text, items = await render(texts.children_list_text, p)
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=t, callback_data=f"child:{i}")]
                                                   for t, i in items]) if items else None
        await message.answer(text, reply_markup=kb)


def _child_kb(cid):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Ko'riklar va kasallik tarixi", callback_data=f"chist:{cid}")],
        [InlineKeyboardButton(text="💉 Emlash kalendari", callback_data=f"cvacc:{cid}")],
    ])


@dp.callback_query(F.data.regexp(r"^(child|chist|cvacc):(\d+)$"))
async def child_cb(cb: CallbackQuery):
    kind, cid = cb.data.split(":")
    child = await mother_child(cb.message.chat.id, int(cid))
    if not child:
        await cb.answer("Ma'lumot topilmadi", show_alert=True)
        return
    fn = {"child": texts.child_card, "chist": texts.child_history, "cvacc": texts.child_vaccinations}[kind]
    await reply_long(cb.message, await render(fn, child), reply_markup=_child_kb(child.id) if kind == "child" else None)
    await cb.answer()


@sync_to_async
def mother_confirm(chat_id, mc_id, yes):
    from apps.alerts.models import MotherConfirmation
    from apps.alerts.mother import handle_response
    mc = MotherConfirmation.objects.select_related("patient__mavze__clinic__district", "author") \
        .filter(pk=mc_id, patient__telegram_chat_id=chat_id).first()   # faqat shu onaning o'z yozuvi
    if not mc:
        return None
    return handle_response(mc, yes)


@dp.callback_query(F.data.regexp(r"^mc:(\d+):(y|n)$"))
async def mc_cb(cb: CallbackQuery):
    _, mc_id, ans = cb.data.split(":")
    res = await mother_confirm(cb.message.chat.id, int(mc_id), ans == "y")
    if res is None:
        await cb.answer("Yozuv topilmadi", show_alert=True)
        return
    label = "✅ Tasdiqlandi" if ans == "y" else "❌ Rad etildi — mutaxassislarga xabar berildi"
    await cb.message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=label, callback_data="noop")]]))
    await cb.answer("Rahmat! Javobingiz qayd etildi." if res else "Javob avval berilgan")


# ---------- Xavf belgilari: ona belgini tanlaydi → saytda qizil signal ----------

@sync_to_async
def danger_subjects(chat_id):
    from apps.dashboard.stats import CHILD_MAX_DAYS
    from datetime import date, timedelta
    p = Patient.objects.filter(telegram_chat_id=chat_id).first()
    if not p:
        return None, []
    kids = list(p.children.filter(birth_date__gte=date.today() - timedelta(days=CHILD_MAX_DAYS)).order_by("birth_date"))
    return p, kids


@dp.message(F.text == BTN_DANGER)
async def danger(message: Message):
    p, kids = await danger_subjects(message.chat.id)
    if not p:
        await start(message, CommandObject(prefix="/", command="start", args=None))
        return
    rows = [[InlineKeyboardButton(text="🤰 O'zim haqimda", callback_data="dg:m")]]
    rows += [[InlineKeyboardButton(text=f"👶 {c.first_name}", callback_data=f"dg:c:{c.id}")] for c in kids]
    await message.answer("🚨 <b>Xavf belgilari</b>\nKim haqida xabar bermoqchisiz?", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


@dp.callback_query(F.data.regexp(r"^dg:(m|c:\d+)$"))
async def danger_pick(cb: CallbackQuery):
    from apps.alerts import danger as dg
    p, kids = await danger_subjects(cb.message.chat.id)
    if not p:
        await cb.answer("Avval /start", show_alert=True)
        return
    if cb.data == "dg:m":
        signs, prefix, who = dg.mother_signs(p), "ds:m", "o'zingizda"
    else:
        cid = int(cb.data.split(":")[2])
        child = next((c for c in kids if c.id == cid), None)
        if not child:
            await cb.answer("Topilmadi", show_alert=True)
            return
        signs, prefix, who = dg.CHILD_SIGNS, f"ds:c:{cid}", f"{child.first_name}da"
    rows = [[InlineKeyboardButton(text=l, callback_data=f"{prefix}:{k}")] for k, l in signs]
    await cb.message.edit_text(f"🚨 <b>Xavf belgilari</b>\nQaysi belgi {who} kuzatilyapti? Tanlang — shifokoringizga darhol xabar boradi.",
                               reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    await cb.answer()


# «Boshqa» tanlansa — keyingi xabar matni signal sifatida yuboriladi: chat_id → child_id (yoki None)
PENDING_OTHER = {}


@sync_to_async
def danger_report(chat_id, child_id, code, note=""):
    from apps.alerts import danger as dg
    p = Patient.objects.select_related("mavze__clinic__district").filter(telegram_chat_id=chat_id).first()
    if not p:
        return None, False
    child = p.children.filter(id=child_id).first() if child_id else None
    if child_id and not child:
        return None, False
    return dg.report(p, code, child, note)


@dp.callback_query(F.data.regexp(r"^ds:(m|c:\d+):([a-z]+)$"))
async def danger_send(cb: CallbackQuery):
    parts = cb.data.split(":")
    child_id, code = (int(parts[2]), parts[3]) if parts[1] == "c" else (None, parts[2])
    if code == "other":
        PENDING_OTHER[cb.message.chat.id] = child_id
        await cb.message.edit_text("📝 <b>Nima bo'layotganini qisqa yozing</b> (masalan: «2 kundan beri oyog'im juda shishgan»).\n"
                                   "Keyingi xabaringiz shifokoringizga signal sifatida yuboriladi. Bekor qilish: /bekor")
        await cb.answer()
        return
    alert, new = await danger_report(cb.message.chat.id, child_id, code)
    if alert is None:
        await cb.answer("Xatolik — qayta urinib ko'ring", show_alert=True)
        return
    head = "✅ <b>Xabaringiz shifokoringizga yuborildi.</b>" if new else "✅ <b>Bu xabar avval yuborilgan</b> — shifokor ko'rmoqda."
    await cb.message.edit_text(
        f"{head}\nTez orada siz bilan bog'lanishadi.\n\n"
        "Ahvol og'ir bo'lsa yoki kuchayib borsa — kutmang, <b>103</b> ga qo'ng'iroq qiling yoki yaqin tibbiyot "
        "muassasasiga boring.")
    await cb.answer("Yuborildi")


@dp.callback_query(F.data == "noop")
async def noop(cb: CallbackQuery):
    await cb.answer()


@dp.message(Command("stop"))
async def stop(message: Message):
    @sync_to_async
    def unlink(chat_id):
        Patient.objects.filter(telegram_chat_id=chat_id).update(telegram_chat_id=None)
    await unlink(message.chat.id)
    await message.answer("Bot uzildi. Qayta ulanish uchun /start", reply_markup=ReplyKeyboardRemove())


@dp.message(F.text == BTN_HELP)
@dp.message(Command("help"))
async def help_(message: Message):
    await message.answer(texts.HELP)


@dp.message(F.text == BTN_AI)
async def ai_intro(message: Message):
    p = await get_patient(message.chat.id)
    if not p:
        await start(message, CommandObject(prefix="/", command="start", args=None))
        return
    await message.answer("🤖 <b>AI yordamchi</b>\nHomiladorlik, chaqaloq parvarishi, ovqatlanish, emlash yoki ko'riklaringiz "
                         "haqida savolingizni oddiy yozing. Masalan:\n• «Homiladorlikda qanday ovqatlar foydali?»\n"
                         "• «Keyingi ko'rigim qachon?»\n• «Chaqaloqni necha marta emizish kerak?»\n\n"
                         "<i>AI tashxis qo'ymaydi va dori yozmaydi. Shoshilinch holatda — 103 yoki «🚨 Xavf belgilari».</i>",
                         reply_markup=MENU)


@sync_to_async
def ai_answer(chat_id, text):
    from .ai_chat import answer
    p = Patient.objects.select_related("mavze__clinic__district").filter(telegram_chat_id=chat_id).first()
    if not p:
        return None, False
    return answer(p, chat_id, text)


@dp.message(Command("bekor"))
async def cancel_other(message: Message):
    PENDING_OTHER.pop(message.chat.id, None)
    await message.answer("Bekor qilindi.", reply_markup=MENU)


@dp.message()
async def fallback(message: Message):
    if message.chat.id in PENDING_OTHER and message.text and not message.text.startswith("/") \
            and message.text not in (BTN_ME, BTN_HISTORY, BTN_KIDS, BTN_UPCOMING, BTN_HELP, BTN_DANGER, BTN_AI):
        child_id = PENDING_OTHER.pop(message.chat.id)
        alert, new = await danger_report(message.chat.id, child_id, "other", message.text)
        if alert is None:
            await message.answer("Xabarni yuborib bo'lmadi — qaytadan «🚨 Xavf belgilari» ni bosing.", reply_markup=MENU)
            return
        await message.answer("✅ <b>Xabaringiz shifokoringizga yuborildi.</b>\nTez orada siz bilan bog'lanishadi.\n\n"
                             "Ahvol og'ir bo'lsa yoki kuchayib borsa — kutmang, <b>103</b> ga qo'ng'iroq qiling yoki yaqin "
                             "tibbiyot muassasasiga boring.", reply_markup=MENU)
        return
    p = await get_patient(message.chat.id)
    if p and message.text and not message.text.startswith("/"):
        from aiogram.enums import ChatAction
        await message.bot.send_chat_action(message.chat.id, ChatAction.TYPING)
        reply, _ = await ai_answer(message.chat.id, message.text)
        await reply_long(message, reply or "Kechirasiz, javob bera olmadim.", reply_markup=MENU)
    elif p:
        await message.answer("Quyidagi bo'limlardan birini tanlang yoki savolingizni yozing 👇", reply_markup=MENU)
    else:
        await start(message, CommandObject(prefix="/", command="start", args=None))


async def main():
    token = settings.TELEGRAM_BOT_TOKEN
    if not token:
        raise SystemExit("TELEGRAM_BOT_TOKEN .env faylida ko'rsatilmagan")
    bot = Bot(token, default=DefaultBotProperties(parse_mode="HTML"))
    me = await bot.get_me()
    log.warning("Bot ishga tushdi: @%s", me.username)
    await dp.start_polling(bot)
