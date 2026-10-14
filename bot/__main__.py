import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, LinkPreviewOptions, MenuButtonWebApp, WebAppInfo

from .config import config
from .db import Database
from .handlers import router
from .reminders import reminders_loop


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    if not config.bot_token:
        raise SystemExit("Вкажи BOT_TOKEN у файлі .env (див. .env.example)")

    db = Database(config.db_path)
    await db.connect()

    bot = Bot(
        config.bot_token,
        default=DefaultBotProperties(
            parse_mode=ParseMode.HTML,
            link_preview=LinkPreviewOptions(is_disabled=True),
        ),
    )
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)
    dp["db"] = db

    await bot.set_my_commands(
        [
            BotCommand(command="start", description="Почати"),
            BotCommand(command="menu", description="🗺 Навігація"),
            BotCommand(command="help", description="ℹ️ Як юзати цей бот?"),
        ]
    )
    if config.trainers_url:
        # Синя кнопка "Тренажери" біля поля вводу
        await bot.set_chat_menu_button(
            menu_button=MenuButtonWebApp(text="Тренажери", web_app=WebAppInfo(url=config.trainers_url))
        )

    reminders = asyncio.create_task(reminders_loop(bot, db))
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        reminders.cancel()
        await db.close()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
