import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

from config import DATABASE
from utils.db import antispam as antispam_db
from utils.db import autorole as autorole_db
from utils.db import dashboard as dashboard_db
from utils.db import makejpc as makejpc_db
from utils.db import migrations as database_migrations
from utils.db import modlogs as modlogs_db
from utils.db import tickets as tickets_db
from utils.db import welcome as welcome_db
from utils.db import youtube as youtube_db


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

    def get_antispam_settings(self, guild_id: int):
        return antispam_db.get_settings(self, guild_id)

    def set_antispam_settings(self, guild_id: int, **values) -> None:
        antispam_db.save_settings(self, guild_id, **values)

    def set_antispam_enabled(self, guild_id: int, enabled: bool) -> None:
        antispam_db.set_enabled(self, guild_id, enabled)

    def get_autorole_settings(self, guild_id: int):
        return autorole_db.get_settings(self, guild_id)

    def set_autorole_settings(
        self,
        guild_id: int,
        role_id: int,
        enabled: bool = True,
    ) -> None:
        autorole_db.save_settings(self, guild_id, role_id, enabled)

    def set_autorole_enabled(self, guild_id: int, enabled: bool) -> None:
        autorole_db.set_enabled(self, guild_id, enabled)

    def get_modlog_settings(self, guild_id: int):
        return modlogs_db.get_settings(self, guild_id)

    def set_modlog_settings(self, guild_id: int, channel_id: int, **values) -> None:
        modlogs_db.save_settings(self, guild_id, channel_id, **values)

    def set_modlog_enabled(self, guild_id: int, enabled: bool) -> None:
        modlogs_db.set_enabled(self, guild_id, enabled)

    def get_ticket_settings(self, guild_id: int):
        return tickets_db.get_settings(self, guild_id)

    def set_ticket_settings(self, guild_id: int, panel_channel_id: int,
                            category_id: int, support_role_id: int,
                            log_channel_id: Optional[int], **values) -> None:
        tickets_db.save_settings(
            self, guild_id, panel_channel_id, category_id,
            support_role_id, log_channel_id, **values,
        )

    def set_ticket_enabled(self, guild_id: int, enabled: bool) -> None:
        tickets_db.set_enabled(self, guild_id, enabled)

    def get_open_ticket(self, guild_id: int, user_id: int):
        return tickets_db.get_open_ticket(self, guild_id, user_id)

    def get_ticket_by_channel(self, channel_id: int):
        return tickets_db.get_ticket_by_channel(self, channel_id)

    def create_ticket_record(self, guild_id: int, channel_id: int,
                             user_id: int, subject: str,
                             description: str) -> None:
        tickets_db.create_ticket(
            self, guild_id, channel_id, user_id, subject, description,
        )

    def claim_ticket_record(self, channel_id: int, user_id: int) -> None:
        tickets_db.claim_ticket(self, channel_id, user_id)

    def close_ticket_record(self, channel_id: int) -> None:
        tickets_db.close_ticket(self, channel_id)

    def _init_db(self):
        database_migrations.initialize(self)

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
        youtube_db.add_channel(self, channel_id, name, url)

    def add_subscription(
        self,
        guild_id: int,
        youtube_channel_id: str,
        discord_channel_id: int,
        mention_role_id: Optional[int] = None,
    ):
        youtube_db.add_subscription(
            self,
            guild_id,
            youtube_channel_id,
            discord_channel_id,
            mention_role_id,
        )

    def remove_subscription(self, guild_id: int, youtube_channel_id: str) -> bool:
        return youtube_db.remove_subscription(
            self, guild_id, youtube_channel_id
        )

    def get_guild_subscriptions(self, guild_id: int):
        return youtube_db.get_guild_subscriptions(self, guild_id)

    def get_enabled_subscriptions(self):
        return youtube_db.get_enabled_subscriptions(self)

    def get_unique_youtube_channels(self):
        return youtube_db.get_unique_channels(self)

    def set_last_video(self, guild_id: int, youtube_channel_id: str, video_id: str):
        youtube_db.set_last_video(
            self, guild_id, youtube_channel_id, video_id
        )

    def youtube_announcement_exists(
        self, guild_id: int, youtube_channel_id: str, video_id: str
    ) -> bool:
        return youtube_db.announcement_exists(
            self, guild_id, youtube_channel_id, video_id
        )

    def mark_youtube_announced(
        self, guild_id: int, youtube_channel_id: str, video_id: str
    ) -> None:
        youtube_db.mark_announced(
            self, guild_id, youtube_channel_id, video_id
        )

    def video_exists(self, video_id: str) -> bool:
        return youtube_db.video_exists(self, video_id)

    def add_video(
        self,
        video_id: str,
        youtube_channel_id: str,
        title: str,
        url: str,
        published_at: Optional[str] = None,
    ):
        youtube_db.add_video(
            self,
            video_id,
            youtube_channel_id,
            title,
            url,
            published_at,
        )

    def pause_subscription(self, guild_id: int, youtube_channel_id: str):
        youtube_db.set_subscription_enabled(
            self, guild_id, youtube_channel_id, False
        )

    def resume_subscription(self, guild_id: int, youtube_channel_id: str):
        youtube_db.set_subscription_enabled(
            self, guild_id, youtube_channel_id, True
        )

    def set_welcome_settings(
        self,
        guild_id: int,
        channel_id: int,
        role_id: Optional[int],
        message: str,
    ):
        welcome_db.set_settings(self, guild_id, channel_id, role_id, message)

    def enable_welcome(self, guild_id: int):
        welcome_db.set_enabled(self, guild_id, True)

    def get_welcome_settings(self, guild_id: int):
        return welcome_db.get_settings(self, guild_id)

    def disable_welcome(self, guild_id: int):
        welcome_db.set_enabled(self, guild_id, False)

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
        dashboard_db.update_welcome_settings(
            self,
            guild_id,
            enabled=enabled,
            channel_id=channel_id,
            message=message,
            embed_title=embed_title,
            embed_color=embed_color,
            dm_enabled=dm_enabled,
        )

    def get_guild_settings(self, guild_id: int):
        return dashboard_db.get_guild_settings(self, guild_id)

    def set_guild_settings(
        self,
        guild_id: int,
        language: str = "cs",
        timezone_name: str = "Europe/Prague",
        command_channel_id: Optional[int] = None,
    ) -> None:
        dashboard_db.set_guild_settings(
            self,
            guild_id,
            language,
            timezone_name,
            command_channel_id,
        )

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
        live_enabled: bool = False,
        live_notify_upcoming: bool = False,
        live_custom_message: str = "🔴 {channel} právě vysílá: {title}\n{url}",
    ) -> None:
        dashboard_db.update_subscription_settings(
            self,
            guild_id,
            youtube_channel_id,
            discord_channel_id=discord_channel_id,
            mention_role_id=mention_role_id,
            enabled=enabled,
            custom_message=custom_message,
            check_interval=check_interval,
            live_enabled=live_enabled,
            live_notify_upcoming=live_notify_upcoming,
            live_custom_message=live_custom_message,
        )

    def count_configured_guilds(self, guild_ids: list[int]) -> int:
        return dashboard_db.count_configured_guilds(self, guild_ids)

    def makejpc_product_exists(self, product_code: str) -> bool:
        return makejpc_db.product_exists(self, product_code)

    def count_makejpc_products(self) -> int:
        return makejpc_db.count_products(self)

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
        makejpc_db.add_product(
            self,
            product_code,
            name,
            price,
            availability,
            product_url,
            image_url,
            announced,
        )

    def update_makejpc_product(
        self,
        product_code: str,
        name: str,
        price: Optional[str],
        availability: Optional[str],
        product_url: str,
        image_url: Optional[str],
    ) -> None:
        makejpc_db.update_product(
            self,
            product_code,
            name,
            price,
            availability,
            product_url,
            image_url,
        )

    def get_makejpc_products(self):
        return makejpc_db.get_products(self)

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
