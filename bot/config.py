import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def _int_or_none(value: str | None) -> int | None:
    value = (value or "").strip()
    return int(value) if value else None


@dataclass(frozen=True)
class Config:
    bot_token: str
    privacy_url: str
    subscription_url: str
    admin_username: str
    premium_channel_id: int | None
    trainers_url: str
    free_unlock_days: int
    db_path: str


config = Config(
    bot_token=os.getenv("BOT_TOKEN", ""),
    privacy_url=os.getenv(
        "PRIVACY_URL",
        "https://docs.google.com/document/d/1UQGuYyYtzok0arH2xxr_xqCce66qYm7dVG37hDJGFL0/edit?usp=sharing",
    ),
    subscription_url=os.getenv("SUBSCRIPTION_URL", "https://base.monobank.ua/sp/9sTVYuCPsjT6M5"),
    admin_username=os.getenv("ADMIN_USERNAME", "ukr_movych").lstrip("@"),
    premium_channel_id=_int_or_none(os.getenv("PREMIUM_CHANNEL_ID")),
    # Тимчасове посилання, поки немає справжніх тренажерів
    trainers_url=os.getenv("TRAINERS_URL", "https://t.me/ukr_movych").strip(),
    free_unlock_days=int(os.getenv("FREE_UNLOCK_DAYS", "10")),
    db_path=os.getenv("DB_PATH", "bot.db"),
)

# Інтервали повторень (у днях після кожного виконаного повторення)
REVIEW_INTERVALS_DAYS = [1, 3, 7, 14, 30]
