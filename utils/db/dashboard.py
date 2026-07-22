"""Databázové operace používané webovým dashboardem."""

from typing import Any, Optional


def update_welcome_settings(
    database: Any,
    guild_id: int,
    *,
    enabled: bool,
    channel_id: Optional[int],
    message: str,
    embed_title: str = "Vítej!",
    embed_color: str = "#5865F2",
    dm_enabled: bool = False,
) -> None:
    with database.connect() as conn:
        conflict = """
            ON CONFLICT (guild_id) DO UPDATE SET
                channel_id = EXCLUDED.channel_id,
                enabled = EXCLUDED.enabled,
                message = EXCLUDED.message,
                embed_title = EXCLUDED.embed_title,
                embed_color = EXCLUDED.embed_color,
                dm_enabled = EXCLUDED.dm_enabled,
                updated_at = EXCLUDED.updated_at
        """ if database.using_postgres else """
            ON CONFLICT(guild_id) DO UPDATE SET
                channel_id = excluded.channel_id,
                enabled = excluded.enabled,
                message = excluded.message,
                embed_title = excluded.embed_title,
                embed_color = excluded.embed_color,
                dm_enabled = excluded.dm_enabled,
                updated_at = excluded.updated_at
        """
        conn.execute(f"""
            INSERT INTO welcome_settings (
                guild_id, channel_id, role_id, enabled, message,
                embed_title, embed_color, dm_enabled, updated_at
            )
            VALUES (?, ?, NULL, ?, ?, ?, ?, ?, ?)
            {conflict}
        """, (
            guild_id,
            channel_id,
            int(enabled),
            message,
            embed_title,
            embed_color,
            int(dm_enabled),
            database.now(),
        ))
        conn.commit()


def get_guild_settings(database: Any, guild_id: int):
    with database.connect() as conn:
        return conn.execute("""
            SELECT *
            FROM guild_settings
            WHERE guild_id = ?
        """, (guild_id,)).fetchone()


def set_guild_settings(
    database: Any,
    guild_id: int,
    language: str = "cs",
    timezone_name: str = "Europe/Prague",
    command_channel_id: Optional[int] = None,
) -> None:
    with database.connect() as conn:
        conflict = """
            ON CONFLICT (guild_id) DO UPDATE SET
                language = EXCLUDED.language,
                timezone = EXCLUDED.timezone,
                command_channel_id = EXCLUDED.command_channel_id,
                updated_at = EXCLUDED.updated_at
        """ if database.using_postgres else """
            ON CONFLICT(guild_id) DO UPDATE SET
                language = excluded.language,
                timezone = excluded.timezone,
                command_channel_id = excluded.command_channel_id,
                updated_at = excluded.updated_at
        """
        conn.execute(f"""
            INSERT INTO guild_settings (
                guild_id, language, timezone,
                command_channel_id, updated_at
            )
            VALUES (?, ?, ?, ?, ?)
            {conflict}
        """, (
            guild_id,
            language,
            timezone_name,
            command_channel_id,
            database.now(),
        ))
        conn.commit()


def update_subscription_settings(
    database: Any,
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
    check_interval = max(60, min(int(check_interval), 3600))
    with database.connect() as conn:
        conn.execute("""
            UPDATE subscriptions
            SET discord_channel_id = ?,
                mention_role_id = ?,
                enabled = ?,
                custom_message = ?,
                check_interval = ?
                , live_enabled = ?
                , live_notify_upcoming = ?
                , live_custom_message = ?
            WHERE guild_id = ? AND youtube_channel_id = ?
        """, (
            discord_channel_id,
            mention_role_id,
            int(enabled),
            custom_message,
            check_interval,
            int(live_enabled),
            int(live_notify_upcoming),
            live_custom_message,
            guild_id,
            youtube_channel_id,
        ))
        conn.commit()


def count_configured_guilds(database: Any, guild_ids: list[int]) -> int:
    if not guild_ids:
        return 0

    total = 0
    for guild_id in guild_ids:
        if database.get_welcome_settings(guild_id) is not None:
            total += 1
            continue
        if database.get_guild_subscriptions(guild_id):
            total += 1
            continue
        if database.get_autorole_settings(guild_id) is not None:
            total += 1
            continue
        if database.get_modlog_settings(guild_id) is not None:
            total += 1
            continue
        if database.get_antispam_settings(guild_id) is not None:
            total += 1
            continue
        if database.get_ticket_settings(guild_id) is not None:
            total += 1
            continue
        if get_guild_settings(database, guild_id) is not None:
            total += 1
    return total
