"""Фонова розсилка нагадувань про повторення."""
import asyncio
import html
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter

from . import keyboards as kb
from . import texts as T
from .db import Database

log = logging.getLogger(__name__)


async def _send_one(bot: Bot, db: Database, user_id: int, topic_id: str) -> None:
    if topic_id.startswith("o"):
        own_id = int(topic_id[1:])
        title = await db.own_topic(user_id, own_id)
        if title is None:
            return
        await bot.send_message(
            user_id, T.review_due(html.escape(title)), reply_markup=kb.own_reminder(own_id)
        )
    else:
        topic = T.TOPICS_BY_ID.get(topic_id)
        if topic is None:
            return
        await bot.send_message(user_id, T.review_due(topic.title), reply_markup=kb.repetition(topic))


async def reminders_loop(bot: Bot, db: Database, interval: int = 60) -> None:
    while True:
        try:
            for user_id, topic_id in await db.due_reminders():
                try:
                    await _send_one(bot, db, user_id, topic_id)
                except TelegramRetryAfter as e:
                    await asyncio.sleep(e.retry_after)
                    continue  # спробуємо в наступному циклі
                except TelegramForbiddenError:
                    await db.delete_user_reps(user_id)  # користувач заблокував бота
                    continue
                except Exception:
                    log.exception("Не вдалося надіслати нагадування %s/%s", user_id, topic_id)
                await db.mark_reminded(user_id, topic_id)
                await asyncio.sleep(0.05)  # не більше ~20 повідомлень/с
        except Exception:
            log.exception("Помилка в циклі нагадувань")
        await asyncio.sleep(interval)
