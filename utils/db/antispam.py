"""Databázové operace AntiSpam modulu."""

from typing import Any


def get_settings(database: Any, guild_id: int):
    with database.connect() as conn:
        return conn.execute(
            "SELECT * FROM antispam_settings WHERE guild_id = ?",
            (guild_id,),
        ).fetchone()


def save_settings(
    database: Any,
    guild_id: int,
    *,
    enabled: bool = True,
    max_messages: int = 6,
    interval_seconds: int = 8,
    duplicate_limit: int = 3,
    mention_limit: int = 5,
    timeout_minutes: int = 10,
    delete_messages: bool = True,
) -> None:
    excluded = "EXCLUDED" if database.using_postgres else "excluded"
    with database.connect() as conn:
        conn.execute(f"""
            INSERT INTO antispam_settings (
                guild_id, enabled, max_messages, interval_seconds,
                duplicate_limit, mention_limit, timeout_minutes,
                delete_messages, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (guild_id) DO UPDATE SET
                enabled = {excluded}.enabled,
                max_messages = {excluded}.max_messages,
                interval_seconds = {excluded}.interval_seconds,
                duplicate_limit = {excluded}.duplicate_limit,
                mention_limit = {excluded}.mention_limit,
                timeout_minutes = {excluded}.timeout_minutes,
                delete_messages = {excluded}.delete_messages,
                updated_at = {excluded}.updated_at
        """, (
            guild_id,
            int(enabled),
            max(3, min(int(max_messages), 20)),
            max(3, min(int(interval_seconds), 60)),
            max(2, min(int(duplicate_limit), 10)),
            max(2, min(int(mention_limit), 20)),
            max(1, min(int(timeout_minutes), 1440)),
            int(delete_messages),
            database.now(),
        ))
        conn.commit()


def set_enabled(database: Any, guild_id: int, enabled: bool) -> None:
    with database.connect() as conn:
        conn.execute("""
            UPDATE antispam_settings
            SET enabled = ?, updated_at = ?
            WHERE guild_id = ?
        """, (int(enabled), database.now(), guild_id))
        conn.commit()
