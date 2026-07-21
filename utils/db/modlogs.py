"""Databázové operace moderačních logů."""

from typing import Any


def get_settings(database: Any, guild_id: int):
    with database.connect() as conn:
        return conn.execute(
            "SELECT * FROM modlog_settings WHERE guild_id = ?",
            (guild_id,),
        ).fetchone()


def save_settings(
    database: Any,
    guild_id: int,
    channel_id: int,
    *,
    enabled: bool = True,
    log_members: bool = True,
    log_messages: bool = True,
    log_voice: bool = True,
    log_channels: bool = True,
    log_bans: bool = True,
) -> None:
    excluded = "EXCLUDED" if database.using_postgres else "excluded"
    with database.connect() as conn:
        conn.execute(f"""
            INSERT INTO modlog_settings (
                guild_id, channel_id, enabled, log_members, log_messages,
                log_voice, log_channels, log_bans, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (guild_id) DO UPDATE SET
                channel_id = {excluded}.channel_id,
                enabled = {excluded}.enabled,
                log_members = {excluded}.log_members,
                log_messages = {excluded}.log_messages,
                log_voice = {excluded}.log_voice,
                log_channels = {excluded}.log_channels,
                log_bans = {excluded}.log_bans,
                updated_at = {excluded}.updated_at
        """, (
            guild_id,
            channel_id,
            int(enabled),
            int(log_members),
            int(log_messages),
            int(log_voice),
            int(log_channels),
            int(log_bans),
            database.now(),
        ))
        conn.commit()


def set_enabled(database: Any, guild_id: int, enabled: bool) -> None:
    with database.connect() as conn:
        conn.execute("""
            UPDATE modlog_settings
            SET enabled = ?, updated_at = ?
            WHERE guild_id = ?
        """, (int(enabled), database.now(), guild_id))
        conn.commit()
