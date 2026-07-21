"""Databázové operace Welcome modulu."""

from typing import Any, Optional


def set_settings(
    database: Any,
    guild_id: int,
    channel_id: int,
    role_id: Optional[int],
    message: str,
) -> None:
    with database.connect() as conn:
        conflict = """
            ON CONFLICT (guild_id) DO UPDATE SET
                channel_id = EXCLUDED.channel_id,
                role_id = EXCLUDED.role_id,
                enabled = 1,
                message = EXCLUDED.message,
                updated_at = EXCLUDED.updated_at
        """ if database.using_postgres else """
            ON CONFLICT(guild_id) DO UPDATE SET
                channel_id = excluded.channel_id,
                role_id = excluded.role_id,
                enabled = 1,
                message = excluded.message,
                updated_at = excluded.updated_at
        """
        conn.execute(f"""
            INSERT INTO welcome_settings
                (guild_id, channel_id, role_id, enabled, message, updated_at)
            VALUES (?, ?, ?, 1, ?, ?)
            {conflict}
        """, (guild_id, channel_id, role_id, message, database.now()))
        conn.commit()


def set_enabled(database: Any, guild_id: int, enabled: bool) -> None:
    with database.connect() as conn:
        conn.execute("""
            UPDATE welcome_settings
            SET enabled = ?,
                updated_at = ?
            WHERE guild_id = ?
        """, (int(enabled), database.now(), guild_id))
        conn.commit()


def get_settings(database: Any, guild_id: int):
    with database.connect() as conn:
        return conn.execute("""
            SELECT *
            FROM welcome_settings
            WHERE guild_id = ?
        """, (guild_id,)).fetchone()
