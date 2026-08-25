import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

from config import DATABASE
from utils.db import antispam as antispam_db
from utils.db import abi_rank as abi_rank_db
from utils.db import autorole as autorole_db
from utils.db import dashboard as dashboard_db
from utils.db import game_deals as game_deals_db
from utils.db import lucky_wheel as lucky_wheel_db
from utils.db import makejpc as makejpc_db
from utils.db import migrations as database_migrations
from utils.db import modlogs as modlogs_db
from utils.db import pc_advice as pc_advice_db
from utils.db import pc_build_challenge as pc_build_challenge_db
from utils.db import reaction_roles as reaction_roles_db
from utils.db import suggestions as suggestions_db
from utils.db import sheep_game as sheep_game_db
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

    def get_reaction_role_settings(self, guild_id: int):
        return reaction_roles_db.get_settings(self, guild_id)

    def save_reaction_role_settings(
        self,
        guild_id: int,
        channel_id: int,
        title: str,
        description: str,
        entries: list[dict],
        *,
        enabled: bool,
    ) -> None:
        reaction_roles_db.save_settings(
            self,
            guild_id,
            channel_id,
            title,
            description,
            entries,
            enabled=enabled,
        )

    def set_reaction_role_message_id(self, guild_id: int, message_id: int) -> None:
        reaction_roles_db.set_message_id(self, guild_id, message_id)

    def get_reaction_role_mapping(self, guild_id: int, message_id: int, emoji: str):
        return reaction_roles_db.get_mapping(self, guild_id, message_id, emoji)

    def get_suggestion_settings(self, guild_id: int):
        return suggestions_db.get_settings(self, guild_id)

    def set_suggestion_settings(self, guild_id: int, channel_id: int, enabled: bool) -> None:
        suggestions_db.save_settings(self, guild_id, channel_id, enabled)

    def create_suggestion(self, *args, **kwargs) -> int:
        return suggestions_db.create_suggestion(self, *args, **kwargs)

    def get_suggestion(self, suggestion_id: int):
        return suggestions_db.get_suggestion(self, suggestion_id)

    def get_open_suggestions(self):
        return suggestions_db.get_open_suggestions(self)

    def get_recent_suggestions(self, guild_id: int, limit: int = 20):
        return suggestions_db.get_recent_suggestions(self, guild_id, limit)

    def set_suggestion_message_id(self, suggestion_id: int, message_id: int) -> None:
        suggestions_db.set_message_id(self, suggestion_id, message_id)

    def vote_suggestion(self, suggestion_id: int, user_id: int, value: int) -> tuple[int, int]:
        return suggestions_db.vote(self, suggestion_id, user_id, value)

    def get_suggestion_vote_totals(self, suggestion_id: int) -> tuple[int, int]:
        return suggestions_db.get_vote_totals(self, suggestion_id)

    def set_suggestion_status(self, suggestion_id: int, status: str, moderator_id: int, response: str = "") -> None:
        suggestions_db.set_status(self, suggestion_id, status, moderator_id, response)

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

    def get_pc_advice_settings(self, guild_id: int):
        return pc_advice_db.get_settings(self, guild_id)

    def set_pc_advice_settings(
        self, guild_id: int, panel_channel_id: int, category_id: int,
        advisor_role_id: int, log_channel_id: Optional[int],
        mode: str = "private", forum_channel_id: Optional[int] = None, **values,
    ) -> None:
        pc_advice_db.save_settings(
            self, guild_id, panel_channel_id, category_id,
            advisor_role_id, log_channel_id, mode, forum_channel_id, **values,
        )

    def set_pc_advice_enabled(self, guild_id: int, enabled: bool) -> None:
        pc_advice_db.set_enabled(self, guild_id, enabled)

    def get_active_pc_advice(self, guild_id: int, user_id: int):
        return pc_advice_db.get_active_for_user(self, guild_id, user_id)

    def get_pc_advice_by_channel(self, channel_id: int):
        return pc_advice_db.get_by_channel(self, channel_id)

    def get_active_pc_advice_for_guild(self, guild_id: int):
        return pc_advice_db.get_active_for_guild(self, guild_id)

    def create_pc_advice_request(
        self, guild_id: int, channel_id: int, user_id: int,
        request_type: str, answers: dict[str, str],
    ) -> None:
        pc_advice_db.create_request(
            self, guild_id, channel_id, user_id, request_type, answers,
        )

    def claim_pc_advice(self, channel_id: int, user_id: int) -> None:
        pc_advice_db.set_claimed(self, channel_id, user_id)

    def resolve_pc_advice(self, channel_id: int) -> None:
        pc_advice_db.set_resolved(self, channel_id)

    def wait_for_pc_advice_user(self, channel_id: int) -> None:
        pc_advice_db.set_waiting_user(self, channel_id)

    def close_pc_advice(self, channel_id: int) -> None:
        pc_advice_db.set_closed(self, channel_id)

    def mark_pc_advice_reminded(self, channel_id: int, message_id: int) -> None:
        pc_advice_db.mark_reminded(self, channel_id, message_id)

    def get_recent_pc_advice(self, guild_id: int, limit: int = 20):
        return pc_advice_db.get_recent(self, guild_id, limit)

    def create_pc_build_challenge(self, *args, **kwargs) -> int:
        return pc_build_challenge_db.create_challenge(self, *args, **kwargs)

    def get_pc_build_challenge(self, challenge_id: int):
        return pc_build_challenge_db.get_challenge(self, challenge_id)

    def get_open_pc_build_challenges(self):
        return pc_build_challenge_db.get_open_challenges(self)

    def get_recent_pc_build_challenges(self, guild_id: int, limit: int = 20):
        return pc_build_challenge_db.get_recent_challenges(self, guild_id, limit)

    def set_pc_build_challenge_message(self, challenge_id: int, message_id: int) -> None:
        pc_build_challenge_db.set_message(self, challenge_id, message_id)

    def set_pc_build_challenge_status(self, challenge_id: int, status: str) -> None:
        pc_build_challenge_db.set_status(self, challenge_id, status)

    def add_pc_build_entry(self, *args, **kwargs) -> bool:
        return pc_build_challenge_db.add_entry(self, *args, **kwargs)

    def get_pc_build_entries(self, challenge_id: int):
        return pc_build_challenge_db.get_entries(self, challenge_id)

    def vote_pc_build_entry(self, challenge_id: int, entry_id: int, user_id: int) -> None:
        pc_build_challenge_db.vote(self, challenge_id, entry_id, user_id)

    def get_pc_build_results(self, challenge_id: int):
        return pc_build_challenge_db.results(self, challenge_id)

    def get_sheep_game_settings(self, guild_id: int):
        return sheep_game_db.get_settings(self, guild_id)

    def set_sheep_game_settings(
        self, guild_id: int, channel_id: Optional[int], enabled: bool
    ) -> None:
        sheep_game_db.save_settings(self, guild_id, channel_id, enabled)

    def record_sheep_count(self, guild_id: int, user_id: int, number: int) -> None:
        sheep_game_db.record_valid_count(self, guild_id, user_id, number)

    def break_sheep_chain(self, guild_id: int, user_id: int) -> int:
        return sheep_game_db.break_chain(self, guild_id, user_id)

    def reset_sheep_chain(self, guild_id: int) -> None:
        sheep_game_db.reset_chain(self, guild_id)

    def get_sheep_leaderboard(self, guild_id: int, limit: int = 10):
        return sheep_game_db.get_leaderboard(self, guild_id, limit)

    def get_lucky_wheel_guild_name(self, guild_id: int) -> str | None:
        return lucky_wheel_db.get_guild_name(self, guild_id)

    def get_lucky_wheel_settings(self, guild_id: int):
        return lucky_wheel_db.get_settings(self, guild_id)

    def save_lucky_wheel_settings(
        self, guild_id: int, title: str, description: str, entries: list[dict]
    ) -> None:
        lucky_wheel_db.save_settings(self, guild_id, title, description, entries)

    def get_game_deal_settings(self, guild_id: int):
        return game_deals_db.get_settings(self, guild_id)

    def get_enabled_game_deal_settings(self):
        return game_deals_db.get_enabled(self)

    def set_game_deal_settings(
        self, guild_id: int, channel_id: Optional[int], mention_role_id: Optional[int],
        enabled_free: bool, enabled_deals: bool, min_discount: int,
        enabled_weekend: bool | None = None, enabled_dlc: bool | None = None,
        store_filters: str | None = None,
    ) -> None:
        game_deals_db.save_settings(
            self, guild_id, channel_id, mention_role_id,
            enabled_free, enabled_deals, min_discount,
            enabled_weekend, enabled_dlc, store_filters,
        )

    def set_game_deal_subscription_role(
        self, guild_id: int, category: str, role_id: Optional[int]
    ) -> bool:
        return game_deals_db.set_subscription_role(self, guild_id, category, role_id)

    def game_deal_seen(self, guild_id: int, source: str, offer_id: str) -> bool:
        return game_deals_db.is_seen(self, guild_id, source, offer_id)

    def mark_game_deal_seen(self, guild_id: int, source: str, offer_id: str) -> None:
        game_deals_db.mark_seen(self, guild_id, source, offer_id)

    def game_deals_initialized(self, guild_id: int, kind: str) -> bool:
        return game_deals_db.is_initialized(self, guild_id, kind)

    def set_game_deals_initialized(self, guild_id: int, kind: str) -> None:
        game_deals_db.set_initialized(self, guild_id, kind)

    def count_seen_game_deals(self, guild_id: int) -> int:
        return game_deals_db.count_seen(self, guild_id)

    def get_game_deal_watches(self, guild_id: int, user_id: int | None = None):
        return game_deals_db.list_watches(self, guild_id, user_id)

    def add_game_deal_watch(self, guild_id: int, user_id: int, query: str) -> bool:
        return game_deals_db.add_watch(self, guild_id, user_id, query)

    def remove_game_deal_watch(self, guild_id: int, user_id: int, query: str) -> bool:
        return game_deals_db.remove_watch(self, guild_id, user_id, query)

    def game_deal_watch_was_notified(
        self, guild_id: int, user_id: int, source: str, offer_id: str
    ) -> bool:
        return game_deals_db.watch_was_notified(self, guild_id, user_id, source, offer_id)

    def mark_game_deal_watch_notified(
        self, guild_id: int, user_id: int, source: str, offer_id: str
    ) -> None:
        game_deals_db.mark_watch_notified(self, guild_id, user_id, source, offer_id)

    def get_abi_rank_settings(self, guild_id: int):
        return abi_rank_db.get_settings(self, guild_id)

    def set_abi_rank_settings(self, guild_id: int, review_channel_id: int,
                              reviewer_role_id: int, rank_roles: dict,
                              enabled: bool = True) -> None:
        abi_rank_db.save_settings(
            self, guild_id, review_channel_id, reviewer_role_id,
            rank_roles, enabled=enabled,
        )

    def set_abi_rank_enabled(self, guild_id: int, enabled: bool) -> None:
        abi_rank_db.set_enabled(self, guild_id, enabled)

    def get_pending_abi_rank(self, guild_id: int, user_id: int):
        return abi_rank_db.get_pending_for_user(self, guild_id, user_id)

    def create_abi_rank_request(self, guild_id: int, user_id: int,
                                game_name: str, game_uid: str, rank_key: str,
                                division: Optional[str], screenshot_url: str) -> int:
        return abi_rank_db.create_request(
            self, guild_id, user_id, game_name, game_uid, rank_key,
            division, screenshot_url,
        )

    def set_abi_rank_review_message(self, request_id: int, message_id: int) -> None:
        abi_rank_db.set_review_message(self, request_id, message_id)

    def get_abi_rank_by_review_message(self, guild_id: int, message_id: int):
        return abi_rank_db.get_by_review_message(self, guild_id, message_id)

    def finish_abi_rank_request(self, request_id: int, status: str,
                                reviewer_id: int,
                                reason: Optional[str] = None) -> None:
        abi_rank_db.finish(self, request_id, status, reviewer_id, reason)

    def get_recent_abi_ranks(self, guild_id: int, limit: int = 20):
        return abi_rank_db.get_recent(self, guild_id, limit)

    def get_abi_rank_leaderboard(self, guild_id: int, limit: int = 20):
        return abi_rank_db.get_leaderboard(self, guild_id, limit)

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
