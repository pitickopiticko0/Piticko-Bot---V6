import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

from config import DATABASE


load_dotenv()

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:
    psycopg = None
    dict_row = None


class PostgresConnection:
    """Adapter, aby zbytek projektu mohl používat sqlite-style ? placeholdery."""

    def __init__(self, database_url: str):
        self.conn = psycopg.connect(database_url, row_factory=dict_row)

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

            conn.execute("""
                CREATE TABLE IF NOT EXISTS guild_settings (
                    guild_id BIGINT PRIMARY KEY,
                    language TEXT NOT NULL DEFAULT 'cs',
                    timezone TEXT NOT NULL DEFAULT 'Europe/Prague',
                    command_channel_id BIGINT,
                    updated_at TEXT NOT NULL
                )
            """)

            # Migrace starších dashboardových tabulek v PostgreSQL.
            conn.execute("""
                ALTER TABLE welcome_settings
                ADD COLUMN IF NOT EXISTS embed_title TEXT NOT NULL DEFAULT 'Vítej!'
            """)
            conn.execute("""
                ALTER TABLE welcome_settings
                ADD COLUMN IF NOT EXISTS embed_color TEXT NOT NULL DEFAULT '#5865F2'
            """)
            conn.execute("""
                ALTER TABLE welcome_settings
                ADD COLUMN IF NOT EXISTS dm_enabled INTEGER NOT NULL DEFAULT 0
            """)
            conn.execute("""
                ALTER TABLE subscriptions
                ADD COLUMN IF NOT EXISTS custom_message TEXT NOT NULL
                DEFAULT '📺 Nové video: {title}\n{url}'
            """)
            conn.execute("""
                ALTER TABLE subscriptions
                ADD COLUMN IF NOT EXISTS check_interval INTEGER NOT NULL DEFAULT 300
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS makejpc_products (
                    product_code TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    price TEXT,
                    availability TEXT,
                    product_url TEXT NOT NULL,
                    image_url TEXT,
                    announced INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
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

            conn.execute("""
                CREATE TABLE IF NOT EXISTS guild_settings (
                    guild_id INTEGER PRIMARY KEY,
                    language TEXT NOT NULL DEFAULT 'cs',
                    timezone TEXT NOT NULL DEFAULT 'Europe/Prague',
                    command_channel_id INTEGER,
                    updated_at TEXT NOT NULL
                )
            """)

            # SQLite neumí ADD COLUMN IF NOT EXISTS. PRAGMA proto běží pouze
            # v SQLite větvi a PostgreSQL se ho nikdy nepokusí zpracovat.
            welcome_columns = {
                row[1]
                for row in conn.execute(
                    "PRAGMA table_info(welcome_settings)"
                ).fetchall()
            }
            if "embed_title" not in welcome_columns:
                conn.execute("""
                    ALTER TABLE welcome_settings
                    ADD COLUMN embed_title TEXT NOT NULL DEFAULT 'Vítej!'
                """)
            if "embed_color" not in welcome_columns:
                conn.execute("""
                    ALTER TABLE welcome_settings
                    ADD COLUMN embed_color TEXT NOT NULL DEFAULT '#5865F2'
                """)
            if "dm_enabled" not in welcome_columns:
                conn.execute("""
                    ALTER TABLE welcome_settings
                    ADD COLUMN dm_enabled INTEGER NOT NULL DEFAULT 0
                """)

            subscription_columns = {
                row[1]
                for row in conn.execute(
                    "PRAGMA table_info(subscriptions)"
                ).fetchall()
            }
            if "custom_message" not in subscription_columns:
                conn.execute("""
                    ALTER TABLE subscriptions
                    ADD COLUMN custom_message TEXT NOT NULL
                    DEFAULT '📺 Nové video: {title}\n{url}'
                """)
            if "check_interval" not in subscription_columns:
                conn.execute("""
                    ALTER TABLE subscriptions
                    ADD COLUMN check_interval INTEGER NOT NULL DEFAULT 300
                """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS makejpc_products (
                    product_code TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    price TEXT,
                    availability TEXT,
                    product_url TEXT NOT NULL,
                    image_url TEXT,
                    announced INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
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

    def update_welcome_settings(
        self,
        guild_id: int,
        *,
        enabled: bool,
        channel_id: Optional[int],
        message: str,
        embed_title: str = "Vítej!",
        embed_color: str = "#5865F2",
        dm_enabled: bool = False,
    ) -> None:
        with self.connect() as conn:
            if self.using_postgres:
                conn.execute("""
                    INSERT INTO welcome_settings (
                        guild_id, channel_id, role_id, enabled, message,
                        embed_title, embed_color, dm_enabled, updated_at
                    )
                    VALUES (?, ?, NULL, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT (guild_id) DO UPDATE SET
                        channel_id = EXCLUDED.channel_id,
                        enabled = EXCLUDED.enabled,
                        message = EXCLUDED.message,
                        embed_title = EXCLUDED.embed_title,
                        embed_color = EXCLUDED.embed_color,
                        dm_enabled = EXCLUDED.dm_enabled,
                        updated_at = EXCLUDED.updated_at
                """, (
                    guild_id,
                    channel_id,
                    int(enabled),
                    message,
                    embed_title,
                    embed_color,
                    int(dm_enabled),
                    self.now(),
                ))
            else:
                conn.execute("""
                    INSERT INTO welcome_settings (
                        guild_id, channel_id, role_id, enabled, message,
                        embed_title, embed_color, dm_enabled, updated_at
                    )
                    VALUES (?, ?, NULL, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(guild_id) DO UPDATE SET
                        channel_id = excluded.channel_id,
                        enabled = excluded.enabled,
                        message = excluded.message,
                        embed_title = excluded.embed_title,
                        embed_color = excluded.embed_color,
                        dm_enabled = excluded.dm_enabled,
                        updated_at = excluded.updated_at
                """, (
                    guild_id,
                    channel_id,
                    int(enabled),
                    message,
                    embed_title,
                    embed_color,
                    int(dm_enabled),
                    self.now(),
                ))
            conn.commit()

    def get_guild_settings(self, guild_id: int):
        with self.connect() as conn:
            return conn.execute("""
                SELECT *
                FROM guild_settings
                WHERE guild_id = ?
            """, (guild_id,)).fetchone()

    def set_guild_settings(
        self,
        guild_id: int,
        language: str = "cs",
        timezone_name: str = "Europe/Prague",
        command_channel_id: Optional[int] = None,
    ) -> None:
        with self.connect() as conn:
            if self.using_postgres:
                conn.execute("""
                    INSERT INTO guild_settings (
                        guild_id, language, timezone,
                        command_channel_id, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT (guild_id) DO UPDATE SET
                        language = EXCLUDED.language,
                        timezone = EXCLUDED.timezone,
                        command_channel_id = EXCLUDED.command_channel_id,
                        updated_at = EXCLUDED.updated_at
                """, (
                    guild_id,
                    language,
                    timezone_name,
                    command_channel_id,
                    self.now(),
                ))
            else:
                conn.execute("""
                    INSERT INTO guild_settings (
                        guild_id, language, timezone,
                        command_channel_id, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(guild_id) DO UPDATE SET
                        language = excluded.language,
                        timezone = excluded.timezone,
                        command_channel_id = excluded.command_channel_id,
                        updated_at = excluded.updated_at
                """, (
                    guild_id,
                    language,
                    timezone_name,
                    command_channel_id,
                    self.now(),
                ))
            conn.commit()

    def update_subscription_settings(
        self,
        guild_id: int,
        youtube_channel_id: str,
        *,
        discord_channel_id: int,
        mention_role_id: Optional[int],
        enabled: bool,
        custom_message: str = "📺 Nové video: {title}\n{url}",
        check_interval: int = 300,
    ) -> None:
        check_interval = max(60, min(int(check_interval), 3600))
        with self.connect() as conn:
            conn.execute("""
                UPDATE subscriptions
                SET discord_channel_id = ?,
                    mention_role_id = ?,
                    enabled = ?,
                    custom_message = ?,
                    check_interval = ?
                WHERE guild_id = ? AND youtube_channel_id = ?
            """, (
                discord_channel_id,
                mention_role_id,
                int(enabled),
                custom_message,
                check_interval,
                guild_id,
                youtube_channel_id,
            ))
            conn.commit()

    def count_configured_guilds(self, guild_ids: list[int]) -> int:
        if not guild_ids:
            return 0

        total = 0
        for guild_id in guild_ids:
            if self.get_welcome_settings(guild_id) is not None:
                total += 1
                continue
            if self.get_guild_subscriptions(guild_id):
                total += 1
                continue
            if self.get_guild_settings(guild_id) is not None:
                total += 1
        return total

    def makejpc_product_exists(self, product_code: str) -> bool:
        with self.connect() as conn:
            return conn.execute(
                "SELECT product_code FROM makejpc_products WHERE product_code = ?",
                (product_code,),
            ).fetchone() is not None

    def count_makejpc_products(self) -> int:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS c FROM makejpc_products"
            ).fetchone()
            return int(row["c"])

    def add_makejpc_product(
        self,
        product_code: str,
        name: str,
        price: Optional[str],
        availability: Optional[str],
        product_url: str,
        image_url: Optional[str],
        announced: bool = False,
    ) -> None:
        now = self.now()
        with self.connect() as conn:
            conn.execute("""
                INSERT INTO makejpc_products (
                    product_code,
                    name,
                    price,
                    availability,
                    product_url,
                    image_url,
                    announced,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                product_code,
                name,
                price,
                availability,
                product_url,
                image_url,
                int(announced),
                now,
                now,
            ))
            conn.commit()

    def update_makejpc_product(
        self,
        product_code: str,
        name: str,
        price: Optional[str],
        availability: Optional[str],
        product_url: str,
        image_url: Optional[str],
    ) -> None:
        with self.connect() as conn:
            conn.execute("""
                UPDATE makejpc_products
                SET name = ?,
                    price = ?,
                    availability = ?,
                    product_url = ?,
                    image_url = ?,
                    updated_at = ?
                WHERE product_code = ?
            """, (
                name,
                price,
                availability,
                product_url,
                image_url,
                self.now(),
                product_code,
            ))
            conn.commit()

    def get_makejpc_products(self):
        with self.connect() as conn:
            return conn.execute("""
                SELECT *
                FROM makejpc_products
                ORDER BY created_at DESC
            """).fetchall()

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
