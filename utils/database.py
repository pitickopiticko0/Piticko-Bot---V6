import os
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

from config import DATABASE
from utils.logger import logger


load_dotenv()

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:
    psycopg = None
    dict_row = None


class PostgresConnection:
    """PostgreSQL adapter s automatickým opakováním připojení."""

    RETRY_DELAYS = (2, 5, 10, 20, 30)

    def __init__(self, database_url: str):
        self.database_url = database_url
        self.conn = self._connect_with_retry()

    def _connect_with_retry(self):
        total_attempts = len(self.RETRY_DELAYS) + 1

        for attempt in range(1, total_attempts + 1):
            try:
                connection = psycopg.connect(
                    self.database_url,
                    row_factory=dict_row,
                    connect_timeout=8,
                )

                if attempt > 1:
                    logger.info(
                        "Připojení k PostgreSQL bylo obnoveno na pokus %s/%s.",
                        attempt,
                        total_attempts,
                    )

                return connection

            except psycopg.OperationalError as error:
                if attempt >= total_attempts:
                    logger.error(
                        "PostgreSQL není dostupné ani po %s pokusech.",
                        total_attempts,
                    )
                    raise

                delay = self.RETRY_DELAYS[attempt - 1]
                logger.warning(
                    "PostgreSQL připojení selhalo (pokus %s/%s): %s. "
                    "Další pokus za %s sekund.",
                    attempt,
                    total_attempts,
                    error,
                    delay,
                )
                time.sleep(delay)

        raise RuntimeError("Připojení k PostgreSQL selhalo.")

    def __enter__(self):
        self.conn.__enter__()
        return self

    def __exit__(self, exc_type, exc, tb):
        return self.conn.__exit__(exc_type, exc, tb)

    def cursor(self):
        return self.conn.cursor()

    def commit(self):
        self.conn.commit()

    def execute(self, query: str, params: tuple = ()):
        query = query.replace("?", "%s")
        return self.conn.execute(query, params)


class Database:
    def __init__(self, db_path: Path = DATABASE):
        self.database_url = os.getenv("DATABASE_URL")
        self.db_path = db_path

        if self.using_postgres:
            if psycopg is None:
                raise RuntimeError(
                    "DATABASE_URL je nastavené, ale chybí psycopg. "
                    "Přidej do requirements.txt: psycopg[binary]>=3.2.0"
                )
        else:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self._init_db()

    @property
    def using_postgres(self) -> bool:
        return bool(self.database_url)

    def connect(self):
        if self.using_postgres:
            return PostgresConnection(self.database_url)

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _init_db(self):
        if self.using_postgres:
            self._init_postgres()
        else:
            self._init_sqlite()

    def _init_postgres(self):
        with self.connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS guilds (
                    guild_id BIGINT PRIMARY KEY,
                    guild_name TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS youtube_channels (
                    youtube_channel_id TEXT PRIMARY KEY,
                    youtube_name TEXT NOT NULL,
                    youtube_url TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS subscriptions (
                    id BIGSERIAL PRIMARY KEY,
                    guild_id BIGINT NOT NULL,
                    youtube_channel_id TEXT NOT NULL,
                    discord_channel_id BIGINT NOT NULL,
                    mention_role_id BIGINT,
                    last_video_id TEXT,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    UNIQUE(guild_id, youtube_channel_id)
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS videos (
                    video_id TEXT PRIMARY KEY,
                    youtube_channel_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    url TEXT NOT NULL,
                    published_at TEXT,
                    announced_at TEXT NOT NULL
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS welcome_settings (
                    guild_id BIGINT PRIMARY KEY,
                    channel_id BIGINT,
                    role_id BIGINT,
                    enabled INTEGER NOT NULL DEFAULT 0,
                    message TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)

            conn.commit()

    def _init_sqlite(self):
        with self.connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS guilds (
                    guild_id INTEGER PRIMARY KEY,
                    guild_name TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS youtube_channels (
                    youtube_channel_id TEXT PRIMARY KEY,
                    youtube_name TEXT NOT NULL,
                    youtube_url TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS subscriptions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    youtube_channel_id TEXT NOT NULL,
                    discord_channel_id INTEGER NOT NULL,
                    mention_role_id INTEGER,
                    last_video_id TEXT,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    UNIQUE(guild_id, youtube_channel_id)
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS videos (
                    video_id TEXT PRIMARY KEY,
                    youtube_channel_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    url TEXT NOT NULL,
                    published_at TEXT,
                    announced_at TEXT NOT NULL
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS welcome_settings (
                    guild_id INTEGER PRIMARY KEY,
                    channel_id INTEGER,
                    role_id INTEGER,
                    enabled INTEGER NOT NULL DEFAULT 0,
                    message TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)

            conn.commit()

    def add_guild(self, guild_id: int, guild_name: str):
        with self.connect() as conn:
            if self.using_postgres:
                conn.execute("""
                    INSERT INTO guilds (guild_id, guild_name, created_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT (guild_id)
                    DO UPDATE SET guild_name = EXCLUDED.guild_name
                """, (guild_id, guild_name, self.now()))
            else:
                conn.execute("""
                    INSERT OR IGNORE INTO guilds (guild_id, guild_name, created_at)
                    VALUES (?, ?, ?)
                """, (guild_id, guild_name, self.now()))

                conn.execute("""
                    UPDATE guilds
                    SET guild_name = ?
                    WHERE guild_id = ?
                """, (guild_name, guild_id))

            conn.commit()

    def add_youtube_channel(self, channel_id: str, name: str, url: str):
        with self.connect() as conn:
            if self.using_postgres:
                conn.execute("""
                    INSERT INTO youtube_channels
                    (youtube_channel_id, youtube_name, youtube_url, created_at)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT (youtube_channel_id)
                    DO UPDATE SET
                        youtube_name = EXCLUDED.youtube_name,
                        youtube_url = EXCLUDED.youtube_url
                """, (channel_id, name, url, self.now()))
            else:
                conn.execute("""
                    INSERT OR REPLACE INTO youtube_channels
                    (youtube_channel_id, youtube_name, youtube_url, created_at)
                    VALUES (?, ?, ?, COALESCE(
                        (SELECT created_at FROM youtube_channels WHERE youtube_channel_id = ?),
                        ?
                    ))
                """, (channel_id, name, url, channel_id, self.now()))

            conn.commit()

    def add_subscription(
        self,
        guild_id: int,
        youtube_channel_id: str,
        discord_channel_id: int,
        mention_role_id: Optional[int] = None,
    ):
        with self.connect() as conn:
            if self.using_postgres:
                conn.execute("""
                    INSERT INTO subscriptions
                    (guild_id, youtube_channel_id, discord_channel_id, mention_role_id, enabled, created_at)
                    VALUES (?, ?, ?, ?, 1, ?)
                    ON CONFLICT (guild_id, youtube_channel_id)
                    DO UPDATE SET
                        discord_channel_id = EXCLUDED.discord_channel_id,
                        mention_role_id = EXCLUDED.mention_role_id,
                        enabled = 1
                """, (
                    guild_id,
                    youtube_channel_id,
                    discord_channel_id,
                    mention_role_id,
                    self.now(),
                ))
            else:
                conn.execute("""
                    INSERT OR REPLACE INTO subscriptions
                    (guild_id, youtube_channel_id, discord_channel_id, mention_role_id, enabled, created_at)
                    VALUES (?, ?, ?, ?, 1, COALESCE(
                        (SELECT created_at FROM subscriptions WHERE guild_id = ? AND youtube_channel_id = ?),
                        ?
                    ))
                """, (
                    guild_id,
                    youtube_channel_id,
                    discord_channel_id,
                    mention_role_id,
                    guild_id,
                    youtube_channel_id,
                    self.now(),
                ))

            conn.commit()

    def remove_subscription(self, guild_id: int, youtube_channel_id: str) -> bool:
        with self.connect() as conn:
            cur = conn.execute("""
                DELETE FROM subscriptions
                WHERE guild_id = ? AND youtube_channel_id = ?
            """, (guild_id, youtube_channel_id))
            conn.commit()
            return cur.rowcount > 0

    def get_guild_subscriptions(self, guild_id: int):
        with self.connect() as conn:
            return conn.execute("""
                SELECT
                    s.*,
                    y.youtube_name,
                    y.youtube_url
                FROM subscriptions s
                JOIN youtube_channels y
                    ON y.youtube_channel_id = s.youtube_channel_id
                WHERE s.guild_id = ?
                ORDER BY y.youtube_name ASC
            """, (guild_id,)).fetchall()

    def get_enabled_subscriptions(self):
        with self.connect() as conn:
            return conn.execute("""
                SELECT
                    s.*,
                    y.youtube_name,
                    y.youtube_url
                FROM subscriptions s
                JOIN youtube_channels y
                    ON y.youtube_channel_id = s.youtube_channel_id
                WHERE s.enabled = 1
            """).fetchall()

    def get_unique_youtube_channels(self):
        with self.connect() as conn:
            return conn.execute("""
                SELECT DISTINCT
                    y.youtube_channel_id,
                    y.youtube_name,
                    y.youtube_url
                FROM youtube_channels y
                JOIN subscriptions s
                    ON s.youtube_channel_id = y.youtube_channel_id
                WHERE s.enabled = 1
            """).fetchall()

    def set_last_video(self, guild_id: int, youtube_channel_id: str, video_id: str):
        with self.connect() as conn:
            conn.execute("""
                UPDATE subscriptions
                SET last_video_id = ?
                WHERE guild_id = ? AND youtube_channel_id = ?
            """, (video_id, guild_id, youtube_channel_id))
            conn.commit()

    def video_exists(self, video_id: str) -> bool:
        with self.connect() as conn:
            row = conn.execute("""
                SELECT video_id
                FROM videos
                WHERE video_id = ?
            """, (video_id,)).fetchone()
            return row is not None

    def add_video(
        self,
        video_id: str,
        youtube_channel_id: str,
        title: str,
        url: str,
        published_at: Optional[str] = None,
    ):
        with self.connect() as conn:
            if self.using_postgres:
                conn.execute("""
                    INSERT INTO videos
                    (video_id, youtube_channel_id, title, url, published_at, announced_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT (video_id) DO NOTHING
                """, (
                    video_id,
                    youtube_channel_id,
                    title,
                    url,
                    published_at,
                    self.now(),
                ))
            else:
                conn.execute("""
                    INSERT OR IGNORE INTO videos
                    (video_id, youtube_channel_id, title, url, published_at, announced_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    video_id,
                    youtube_channel_id,
                    title,
                    url,
                    published_at,
                    self.now(),
                ))

            conn.commit()

    def pause_subscription(self, guild_id: int, youtube_channel_id: str):
        with self.connect() as conn:
            conn.execute("""
                UPDATE subscriptions
                SET enabled = 0
                WHERE guild_id = ? AND youtube_channel_id = ?
            """, (guild_id, youtube_channel_id))
            conn.commit()

    def resume_subscription(self, guild_id: int, youtube_channel_id: str):
        with self.connect() as conn:
            conn.execute("""
                UPDATE subscriptions
                SET enabled = 1
                WHERE guild_id = ? AND youtube_channel_id = ?
            """, (guild_id, youtube_channel_id))
            conn.commit()

    def set_welcome_settings(
        self,
        guild_id: int,
        channel_id: int,
        role_id: Optional[int],
        message: str,
    ):
        with self.connect() as conn:
            if self.using_postgres:
                conn.execute("""
                    INSERT INTO welcome_settings
                    (guild_id, channel_id, role_id, enabled, message, updated_at)
                    VALUES (?, ?, ?, 1, ?, ?)
                    ON CONFLICT (guild_id)
                    DO UPDATE SET
                        channel_id = EXCLUDED.channel_id,
                        role_id = EXCLUDED.role_id,
                        enabled = 1,
                        message = EXCLUDED.message,
                        updated_at = EXCLUDED.updated_at
                """, (
                    guild_id,
                    channel_id,
                    role_id,
                    message,
                    self.now(),
                ))
            else:
                conn.execute("""
                    INSERT OR REPLACE INTO welcome_settings
                    (guild_id, channel_id, role_id, enabled, message, updated_at)
                    VALUES (?, ?, ?, 1, ?, ?)
                """, (
                    guild_id,
                    channel_id,
                    role_id,
                    message,
                    self.now(),
                ))

            conn.execute("""
                UPDATE welcome_settings
                SET enabled = 1,
                    updated_at = ?
                WHERE guild_id = ?
            """, (self.now(), guild_id))

            conn.commit()

    def enable_welcome(self, guild_id: int):
        with self.connect() as conn:
            conn.execute("""
                UPDATE welcome_settings
                SET enabled = 1,
                    updated_at = ?
                WHERE guild_id = ?
            """, (self.now(), guild_id))
            conn.commit()

    def get_welcome_settings(self, guild_id: int):
        with self.connect() as conn:
            return conn.execute("""
                SELECT *
                FROM welcome_settings
                WHERE guild_id = ?
            """, (guild_id,)).fetchone()

    def disable_welcome(self, guild_id: int):
        with self.connect() as conn:
            conn.execute("""
                UPDATE welcome_settings
                SET enabled = 0,
                    updated_at = ?
                WHERE guild_id = ?
            """, (self.now(), guild_id))
            conn.commit()

    def stats(self):
        with self.connect() as conn:
            guilds = conn.execute("SELECT COUNT(*) AS c FROM guilds").fetchone()["c"]
            channels = conn.execute("SELECT COUNT(*) AS c FROM youtube_channels").fetchone()["c"]
            subs = conn.execute("SELECT COUNT(*) AS c FROM subscriptions").fetchone()["c"]
            videos = conn.execute("SELECT COUNT(*) AS c FROM videos").fetchone()["c"]

            return {
                "guilds": guilds,
                "youtube_channels": channels,
                "subscriptions": subs,
                "videos": videos,
            }


db = Database()
