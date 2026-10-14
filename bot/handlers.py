"""Обробники. Кожне натискання кнопки РЕДАГУЄ поточне повідомлення,
а не надсилає нове — тож у чаті завжди один «живий» екран."""
import asyncio
import html
import random
import time
from datetime import datetime, timedelta, timezone

from aiogram import Bot, F, Router
from aiogram.enums import ChatMemberStatus
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InaccessibleMessage, InlineKeyboardMarkup, Message

from . import keyboards as kb
from . import texts as T
from .config import REVIEW_INTERVALS_DAYS, config
from .db import DAY, Database

router = Router()

try:
    from zoneinfo import ZoneInfo

    TZ = ZoneInfo("Europe/Kyiv")
except Exception:  # немає tzdata (напр., Windows без пакета tzdata)
    TZ = timezone(timedelta(hours=3))


def fmt_date(ts: int | None) -> str | None:
    if ts is None:
        return None
    return datetime.fromtimestamp(ts, TZ).strftime("%d.%m")


class OwnInput(StatesGroup):
    title = State()


# ---------- показ екрана: редагування на місці ----------


async def show(call: CallbackQuery, text: str, markup: InlineKeyboardMarkup) -> None:
    # Відповідаємо на callback паралельно з редагуванням — «годинник» на кнопці зникає миттєво
    answer = asyncio.ensure_future(call.answer())
    msg = call.message
    try:
        if msg is None or isinstance(msg, InaccessibleMessage):
            raise LookupError
        await msg.edit_text(text, reply_markup=markup)
    except TelegramBadRequest as e:
        if "message is not modified" not in e.message:
            await call.bot.send_message(call.from_user.id, text, reply_markup=markup)
    except LookupError:
        await call.bot.send_message(call.from_user.id, text, reply_markup=markup)
    await asyncio.gather(answer, return_exceptions=True)


# ---------- доступ до тем (базовий режим / підписка) ----------

_premium_cache: dict[int, tuple[bool, float]] = {}


async def is_premium(bot: Bot, user_id: int) -> bool:
    if config.premium_channel_id is None:
        return False
    cached = _premium_cache.get(user_id)
    if cached and time.monotonic() - cached[1] < 300:
        return cached[0]
    try:
        member = await bot.get_chat_member(config.premium_channel_id, user_id)
        ok = member.status in (
            ChatMemberStatus.MEMBER,
            ChatMemberStatus.ADMINISTRATOR,
            ChatMemberStatus.CREATOR,
        ) or (member.status == ChatMemberStatus.RESTRICTED and getattr(member, "is_member", False))
    except TelegramBadRequest:
        ok = False
    _premium_cache[user_id] = (ok, time.monotonic())
    return ok


async def try_unlock(bot: Bot, db: Database, user_id: int, topic_id: str) -> int | None:
    """Відкриває тему. Повертає None, якщо доступ є, або час, коли можна відкрити наступну."""
    if await db.is_unlocked(user_id, topic_id):
        return None
    last = await db.last_unlock_at(user_id)
    available_at = (last or 0) + config.free_unlock_days * DAY
    if available_at <= time.time() or await is_premium(bot, user_id):
        await db.unlock(user_id, topic_id)
        return None
    return available_at


# ---------- команди ----------


@router.message(CommandStart())
async def cmd_start(message: Message, db: Database, state: FSMContext) -> None:
    await state.clear()
    await db.add_user(message.from_user.id)
    await message.answer(T.WELCOME, reply_markup=kb.welcome())


@router.message(Command("menu"))
async def cmd_menu(message: Message, db: Database, state: FSMContext) -> None:
    await state.clear()
    await db.add_user(message.from_user.id)
    await message.answer(T.NAV, reply_markup=kb.nav())


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(T.HELP, reply_markup=kb.back_to_nav())


# ---------- головні екрани ----------


@router.callback_query(F.data == "features")
async def cb_features(call: CallbackQuery) -> None:
    await show(call, T.FEATURES, kb.features())


@router.callback_query(F.data == "nav")
async def cb_nav(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await show(call, T.NAV, kb.nav())


@router.callback_query(F.data.startswith("tp:"))
async def cb_topics(call: CallbackQuery) -> None:
    _, mode, page = call.data.split(":")
    title = T.TOPICS_REPEAT if mode == "r" else T.TOPICS_MATERIALS
    await show(call, title, kb.topics(mode, int(page)))


@router.callback_query(F.data == "admins")
async def cb_admins(call: CallbackQuery) -> None:
    await show(call, T.ADMINS, kb.admins())


@router.callback_query(F.data == "help")
async def cb_help(call: CallbackQuery) -> None:
    await show(call, T.HELP, kb.back_to_nav())


# ---------- інтервальне повторення ----------


async def repetition_screen(call: CallbackQuery, db: Database, topic: T.Topic) -> None:
    user_id = call.from_user.id
    rep = await db.get_rep(user_id, topic.id)
    if rep is None:
        available_at = await try_unlock(call.bot, db, user_id, topic.id)
        if available_at is not None:
            await show(call, T.limit_reached(fmt_date(available_at)), kb.limit())
            return
        await db.start_rep(user_id, topic.id)
        await show(call, T.repetition_started(topic.title), kb.repetition(topic))
        return

    stage, next_at = rep
    if next_at is not None and next_at <= time.time():
        text = T.repetition_started(topic.title) if stage == 0 else T.review_due(topic.title)
    else:
        text = T.repetition_status(
            topic.title, stage, len(REVIEW_INTERVALS_DAYS), fmt_date(next_at)
        )
    await show(call, text, kb.repetition(topic))


@router.callback_query(F.data.startswith("rs:"))
async def cb_rep_start(call: CallbackQuery, db: Database) -> None:
    topic = T.TOPICS_BY_ID.get(call.data[3:])
    if topic is None:
        await call.answer()
        return
    await repetition_screen(call, db, topic)


@router.callback_query(F.data.startswith("do:"))
async def cb_do_review(call: CallbackQuery, db: Database) -> None:
    topic = T.TOPICS_BY_ID.get(call.data[3:])
    if topic is None:
        await call.answer()
        return
    user_id = call.from_user.id
    if await db.get_rep(user_id, topic.id) is None:
        # кнопка зі старого повідомлення: спершу запускаємо повторення
        await repetition_screen(call, db, topic)
        return
    result = await db.complete_review(user_id, topic.id)
    text = topic.material or T.material_placeholder(topic.title)
    if result is not False:
        text += "\n\n" + T.review_done(topic.title, fmt_date(result))
    await show(call, text, kb.material(topic, back=f"rs:{topic.id}"))


@router.callback_query(F.data.startswith("test:"))
async def cb_test(call: CallbackQuery) -> None:
    topic = T.TOPICS_BY_ID.get(call.data[5:])
    if topic is None:
        await call.answer()
        return
    await show(call, T.test_placeholder(topic.title), kb.test_back(topic))


# ---------- допоміжні матеріали ----------


@router.callback_query(F.data.startswith("ms:"))
async def cb_material(call: CallbackQuery, db: Database) -> None:
    topic = T.TOPICS_BY_ID.get(call.data[3:])
    if topic is None:
        await call.answer()
        return
    available_at = await try_unlock(call.bot, db, call.from_user.id, topic.id)
    if available_at is not None:
        await show(call, T.limit_reached(fmt_date(available_at)), kb.limit())
        return
    text = topic.material or T.material_placeholder(topic.title)
    await show(call, text, kb.material_from_list(topic))


# ---------- порада ----------


@router.callback_query(F.data == "tip")
async def cb_tip(call: CallbackQuery, db: Database) -> None:
    started = await db.started_topics(call.from_user.id)
    candidates = [t for t in T.TOPICS if t.id not in started]
    if not candidates:
        await show(call, T.TIP_ALL_DONE, kb.back_to_nav())
        return
    topic = random.choice(candidates)
    await show(call, T.TIP.format(title=topic.title), kb.tip(topic))


# ---------- повторювати своє ----------


async def own_screen(db: Database, user_id: int, prefix: str = ""):
    items = await db.own_topics(user_id)
    if items:
        lines = "\n".join(f"• {html.escape(title)}" for _, title in items)
        text = T.OWN_LIST.format(items=lines)
    else:
        text = T.OWN_LIST_EMPTY
    if prefix:
        text = prefix + "\n\n" + text
    return text, kb.own_list(items)


@router.callback_query(F.data == "own")
async def cb_own(call: CallbackQuery, db: Database, state: FSMContext) -> None:
    await state.clear()
    text, markup = await own_screen(db, call.from_user.id)
    await show(call, text, markup)


@router.callback_query(F.data == "oa")
async def cb_own_add(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(OwnInput.title)
    if call.message and not isinstance(call.message, InaccessibleMessage):
        await state.update_data(screen_id=call.message.message_id)
    await show(call, T.OWN_ASK, kb.own_cancel())


@router.message(StateFilter(OwnInput.title), F.text)
async def own_title_input(message: Message, db: Database, state: FSMContext, bot: Bot) -> None:
    user_id = message.from_user.id
    title = message.text.strip()[:100]
    safe_title = html.escape(title)
    data = await state.get_data()
    await state.clear()

    own_id = await db.add_own_topic(user_id, title)
    await db.start_rep(user_id, f"o{own_id}", first_in_days=1)
    text, markup = await own_screen(db, user_id, prefix=T.OWN_ADDED.format(title=safe_title))

    # Прибираємо введене повідомлення й оновлюємо той самий екран
    try:
        await message.delete()
    except TelegramBadRequest:
        pass
    screen_id = data.get("screen_id")
    try:
        if screen_id is None:
            raise LookupError
        await bot.edit_message_text(
            text, chat_id=message.chat.id, message_id=screen_id, reply_markup=markup
        )
    except (TelegramBadRequest, LookupError):
        await message.answer(text, reply_markup=markup)


@router.callback_query(F.data.startswith("od:"))
async def cb_own_delete(call: CallbackQuery, db: Database) -> None:
    own_id = int(call.data[3:])
    title = await db.own_topic(call.from_user.id, own_id)
    prefix = ""
    if title is not None:
        await db.delete_own_topic(call.from_user.id, own_id)
        prefix = T.OWN_REMOVED.format(title=html.escape(title))
    text, markup = await own_screen(db, call.from_user.id, prefix=prefix)
    await show(call, text, markup)


@router.callback_query(F.data.startswith("oc:"))
async def cb_own_complete(call: CallbackQuery, db: Database) -> None:
    own_id = int(call.data[3:])
    title = await db.own_topic(call.from_user.id, own_id)
    if title is None:
        await show(call, T.OWN_LIST_EMPTY, kb.back_to_nav())
        return
    title = html.escape(title)
    result = await db.complete_review(call.from_user.id, f"o{own_id}")
    if result is False:
        rep = await db.get_rep(call.from_user.id, f"o{own_id}")
        text = T.repetition_status(
            title, rep[0] if rep else 0, len(REVIEW_INTERVALS_DAYS), fmt_date(rep[1] if rep else None)
        )
    else:
        text = T.review_done(title, fmt_date(result))
    await show(call, text, kb.back_to_nav())


# ---------- будь-що інше ----------


@router.message(F.text & ~F.text.startswith("/"))
async def any_text(message: Message) -> None:
    await message.answer(T.NAV, reply_markup=kb.nav())


@router.callback_query()
async def cb_unknown(call: CallbackQuery) -> None:
    await call.answer()
