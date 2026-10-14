import time

import aiosqlite

from .config import REVIEW_INTERVALS_DAYS

DAY = 86400

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    created_at INTEGER NOT NULL
);
-- Теми, які користувач уже відкрив (для ліміту базового режиму)
CREATE TABLE IF NOT EXISTS unlocks (
    user_id INTEGER NOT NULL,
    topic_id TEXT NOT NULL,
    at INTEGER NOT NULL,
    PRIMARY KEY (user_id, topic_id)
);
-- Інтервальні повторення. topic_id: id теми або "o<id>" для власних тем
CREATE TABLE IF NOT EXISTS reps (
    user_id INTEGER NOT NULL,
    topic_id TEXT NOT NULL,
    stage INTEGER NOT NULL DEFAULT 0,
    next_at INTEGER,
    reminded INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (user_id, topic_id)
);
CREATE INDEX IF NOT EXISTS reps_due ON reps (reminded, next_at);
CREATE TABLE IF NOT EXISTS own_topics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    title TEXT NOT NULL
);
"""


class Database:
    def __init__(self, path: str):
        self.path = path
        self.conn: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        self.conn = await aiosqlite.connect(self.path)
        await self.conn.execute("PRAGMA journal_mode=WAL")
        await self.conn.executescript(SCHEMA)
        await self.conn.commit()

    async def close(self) -> None:
        if self.conn:
            await self.conn.close()

    async def add_user(self, user_id: int) -> None:
        await self.conn.execute(
            "INSERT OR IGNORE INTO users (user_id, created_at) VALUES (?, ?)",
            (user_id, int(time.time())),
        )
        await self.conn.commit()

    # ----- ліміт тем -----

    async def is_unlocked(self, user_id: int, topic_id: str) -> bool:
        cur = await self.conn.execute(
            "SELECT 1 FROM unlocks WHERE user_id = ? AND topic_id = ?", (user_id, topic_id)
        )
        return await cur.fetchone() is not None

    async def last_unlock_at(self, user_id: int) -> int | None:
        cur = await self.conn.execute("SELECT MAX(at) FROM unlocks WHERE user_id = ?", (user_id,))
        row = await cur.fetchone()
        return row[0] if row else None

    async def unlock(self, user_id: int, topic_id: str) -> None:
        await self.conn.execute(
            "INSERT OR IGNORE INTO unlocks (user_id, topic_id, at) VALUES (?, ?, ?)",
            (user_id, topic_id, int(time.time())),
        )
        await self.conn.commit()

    # ----- повторення -----

    async def get_rep(self, user_id: int, topic_id: str) -> tuple[int, int | None] | None:
        cur = await self.conn.execute(
            "SELECT stage, next_at FROM reps WHERE user_id = ? AND topic_id = ?",
            (user_id, topic_id),
        )
        return await cur.fetchone()

    async def started_topics(self, user_id: int) -> set[str]:
        cur = await self.conn.execute("SELECT topic_id FROM reps WHERE user_id = ?", (user_id,))
        return {row[0] for row in await cur.fetchall()}

    async def start_rep(self, user_id: int, topic_id: str, first_in_days: int = 0) -> None:
        """Перше повторення доступне одразу (або через first_in_days з нагадуванням)."""
        next_at = int(time.time()) + first_in_days * DAY
        await self.conn.execute(
            "INSERT OR IGNORE INTO reps (user_id, topic_id, stage, next_at, reminded) "
            "VALUES (?, ?, 0, ?, ?)",
            (user_id, topic_id, next_at, 0 if first_in_days else 1),
        )
        await self.conn.commit()

    async def complete_review(self, user_id: int, topic_id: str) -> int | None | bool:
        """Зараховує повторення, якщо воно вже настало.

        Повертає новий next_at (None — усі етапи пройдено) або False, якщо ще зарано.
        """
        rep = await self.get_rep(user_id, topic_id)
        if rep is None:
            return False
        stage, next_at = rep
        now = int(time.time())
        if next_at is None or next_at > now:
            return False
        stage += 1
        new_next = (
            now + REVIEW_INTERVALS_DAYS[stage - 1] * DAY
            if stage <= len(REVIEW_INTERVALS_DAYS)
            else None
        )
        await self.conn.execute(
            "UPDATE reps SET stage = ?, next_at = ?, reminded = 0 WHERE user_id = ? AND topic_id = ?",
            (stage, new_next, user_id, topic_id),
        )
        await self.conn.commit()
        return new_next

    async def due_reminders(self, limit: int = 100) -> list[tuple[int, str]]:
        cur = await self.conn.execute(
            "SELECT user_id, topic_id FROM reps "
            "WHERE reminded = 0 AND next_at IS NOT NULL AND next_at <= ? LIMIT ?",
            (int(time.time()), limit),
        )
        return await cur.fetchall()

    async def mark_reminded(self, user_id: int, topic_id: str) -> None:
        await self.conn.execute(
            "UPDATE reps SET reminded = 1 WHERE user_id = ? AND topic_id = ?", (user_id, topic_id)
        )
        await self.conn.commit()

    async def delete_user_reps(self, user_id: int) -> None:
        await self.conn.execute("DELETE FROM reps WHERE user_id = ?", (user_id,))
        await self.conn.commit()

    # ----- власні теми -----

    async def own_topics(self, user_id: int) -> list[tuple[int, str]]:
        cur = await self.conn.execute(
            "SELECT id, title FROM own_topics WHERE user_id = ? ORDER BY id", (user_id,)
        )
        return await cur.fetchall()

    async def own_topic(self, user_id: int, own_id: int) -> str | None:
        cur = await self.conn.execute(
            "SELECT title FROM own_topics WHERE id = ? AND user_id = ?", (own_id, user_id)
        )
        row = await cur.fetchone()
        return row[0] if row else None

    async def add_own_topic(self, user_id: int, title: str) -> int:
        cur = await self.conn.execute(
            "INSERT INTO own_topics (user_id, title) VALUES (?, ?)", (user_id, title)
        )
        await self.conn.commit()
        return cur.lastrowid

    async def delete_own_topic(self, user_id: int, own_id: int) -> None:
        await self.conn.execute(
            "DELETE FROM own_topics WHERE id = ? AND user_id = ?", (own_id, user_id)
        )
        await self.conn.execute(
            "DELETE FROM reps WHERE user_id = ? AND topic_id = ?", (user_id, f"o{own_id}")
        )
        await self.conn.commit()
