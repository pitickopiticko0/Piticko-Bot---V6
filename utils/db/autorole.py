"""Databázové operace AutoRole modulu."""

from typing import Any


def get_settings(database: Any, guild_id: int):
    with database.connect() as conn:
        return conn.execute("""
            SELECT * FROM autorole_settings WHERE guild_id = ?
        """, (guild_id,)).fetchone()


def save_settings(
    database: Any,
    guild_id: int,
    role_id: int,
    enabled: bool = True,
) -> None:
    excluded = "EXCLUDED" if database.using_postgres else "excluded"
    with database.connect() as conn:
        conn.execute(f"""
            INSERT INTO autorole_settings
                (guild_id, role_id, enabled, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT (guild_id) DO UPDATE SET
                role_id = {excluded}.role_id,
                enabled = {excluded}.enabled,
                updated_at = {excluded}.updated_at
        """, (guild_id, role_id, int(enabled), database.now()))
        conn.commit()


def set_enabled(database: Any, guild_id: int, enabled: bool) -> None:
    with database.connect() as conn:
        conn.execute("""
            UPDATE autorole_settings
            SET enabled = ?, updated_at = ?
            WHERE guild_id = ?
        """, (int(enabled), database.now(), guild_id))
        conn.commit()
