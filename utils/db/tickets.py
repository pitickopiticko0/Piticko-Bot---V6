"""Databázové operace Ticket systému."""

from typing import Any, Optional


def get_settings(database: Any, guild_id: int):
    with database.connect() as conn:
        return conn.execute(
            "SELECT * FROM ticket_settings WHERE guild_id = ?",
            (guild_id,),
        ).fetchone()


def save_settings(
    database: Any,
    guild_id: int,
    panel_channel_id: int,
    category_id: int,
    support_role_id: int,
    log_channel_id: Optional[int],
    *,
    enabled: bool = True,
) -> None:
    excluded = "EXCLUDED" if database.using_postgres else "excluded"
    with database.connect() as conn:
        conn.execute(f"""
            INSERT INTO ticket_settings (
                guild_id, panel_channel_id, category_id, support_role_id,
                log_channel_id, enabled, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (guild_id) DO UPDATE SET
                panel_channel_id = {excluded}.panel_channel_id,
                category_id = {excluded}.category_id,
                support_role_id = {excluded}.support_role_id,
                log_channel_id = {excluded}.log_channel_id,
                enabled = {excluded}.enabled,
                updated_at = {excluded}.updated_at
        """, (
            guild_id, panel_channel_id, category_id, support_role_id,
            log_channel_id, int(enabled), database.now(),
        ))
        conn.commit()


def set_enabled(database: Any, guild_id: int, enabled: bool) -> None:
    with database.connect() as conn:
        conn.execute("""
            UPDATE ticket_settings SET enabled = ?, updated_at = ?
            WHERE guild_id = ?
        """, (int(enabled), database.now(), guild_id))
        conn.commit()


def get_open_ticket(database: Any, guild_id: int, user_id: int):
    with database.connect() as conn:
        return conn.execute("""
            SELECT * FROM tickets
            WHERE guild_id = ? AND user_id = ? AND status = 'open'
            ORDER BY id DESC LIMIT 1
        """, (guild_id, user_id)).fetchone()


def get_ticket_by_channel(database: Any, channel_id: int):
    with database.connect() as conn:
        return conn.execute("""
            SELECT * FROM tickets
            WHERE channel_id = ? AND status = 'open'
        """, (channel_id,)).fetchone()


def create_ticket(
    database: Any,
    guild_id: int,
    channel_id: int,
    user_id: int,
    subject: str,
    description: str,
) -> None:
    with database.connect() as conn:
        conn.execute("""
            INSERT INTO tickets
                (guild_id, channel_id, user_id, subject, description,
                 status, created_at)
            VALUES (?, ?, ?, ?, ?, 'open', ?)
        """, (
            guild_id, channel_id, user_id, subject, description,
            database.now(),
        ))
        conn.commit()


def claim_ticket(database: Any, channel_id: int, user_id: int) -> None:
    with database.connect() as conn:
        conn.execute(
            "UPDATE tickets SET claimed_by = ? WHERE channel_id = ?",
            (user_id, channel_id),
        )
        conn.commit()


def close_ticket(database: Any, channel_id: int) -> None:
    with database.connect() as conn:
        conn.execute("""
            UPDATE tickets SET status = 'closed', closed_at = ?
            WHERE channel_id = ?
        """, (database.now(), channel_id))
        conn.commit()
