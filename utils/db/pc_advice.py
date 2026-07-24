"""Databázové operace PC poradny."""

import json
from typing import Any, Optional


def get_settings(database: Any, guild_id: int):
    with database.connect() as conn:
        return conn.execute(
            "SELECT * FROM pc_advice_settings WHERE guild_id = ?", (guild_id,)
        ).fetchone()


def save_settings(
    database: Any,
    guild_id: int,
    panel_channel_id: int,
    category_id: int,
    advisor_role_id: int,
    log_channel_id: Optional[int],
    *,
    enabled: bool = True,
) -> None:
    excluded = "EXCLUDED" if database.using_postgres else "excluded"
    with database.connect() as conn:
        conn.execute(f"""
            INSERT INTO pc_advice_settings
                (guild_id, panel_channel_id, category_id, advisor_role_id,
                 log_channel_id, enabled, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (guild_id) DO UPDATE SET
                panel_channel_id = {excluded}.panel_channel_id,
                category_id = {excluded}.category_id,
                advisor_role_id = {excluded}.advisor_role_id,
                log_channel_id = {excluded}.log_channel_id,
                enabled = {excluded}.enabled,
                updated_at = {excluded}.updated_at
        """, (
            guild_id, panel_channel_id, category_id, advisor_role_id,
            log_channel_id, int(enabled), database.now(),
        ))
        conn.commit()


def set_enabled(database: Any, guild_id: int, enabled: bool) -> None:
    with database.connect() as conn:
        conn.execute(
            "UPDATE pc_advice_settings SET enabled = ?, updated_at = ? WHERE guild_id = ?",
            (int(enabled), database.now(), guild_id),
        )
        conn.commit()


def get_active_for_user(database: Any, guild_id: int, user_id: int):
    with database.connect() as conn:
        return conn.execute("""
            SELECT * FROM pc_advice_requests
            WHERE guild_id = ? AND user_id = ? AND status IN ('open', 'resolved')
            ORDER BY id DESC LIMIT 1
        """, (guild_id, user_id)).fetchone()


def get_by_channel(database: Any, channel_id: int):
    with database.connect() as conn:
        return conn.execute(
            "SELECT * FROM pc_advice_requests WHERE channel_id = ?", (channel_id,)
        ).fetchone()


def create_request(
    database: Any, guild_id: int, channel_id: int, user_id: int,
    request_type: str, answers: dict[str, str],
) -> None:
    with database.connect() as conn:
        conn.execute("""
            INSERT INTO pc_advice_requests
                (guild_id, channel_id, user_id, request_type, answers, status, created_at)
            VALUES (?, ?, ?, ?, ?, 'open', ?)
        """, (
            guild_id, channel_id, user_id, request_type,
            json.dumps(answers, ensure_ascii=False), database.now(),
        ))
        conn.commit()


def set_claimed(database: Any, channel_id: int, user_id: int) -> None:
    with database.connect() as conn:
        conn.execute(
            "UPDATE pc_advice_requests SET claimed_by = ? WHERE channel_id = ?",
            (user_id, channel_id),
        )
        conn.commit()


def set_resolved(database: Any, channel_id: int) -> None:
    with database.connect() as conn:
        conn.execute("""
            UPDATE pc_advice_requests
            SET status = 'resolved', resolved_at = ? WHERE channel_id = ?
        """, (database.now(), channel_id))
        conn.commit()


def set_closed(database: Any, channel_id: int) -> None:
    with database.connect() as conn:
        conn.execute("""
            UPDATE pc_advice_requests
            SET status = 'closed', closed_at = ? WHERE channel_id = ?
        """, (database.now(), channel_id))
        conn.commit()


def get_recent(database: Any, guild_id: int, limit: int = 20):
    with database.connect() as conn:
        return conn.execute("""
            SELECT * FROM pc_advice_requests
            WHERE guild_id = ? ORDER BY id DESC LIMIT ?
        """, (guild_id, limit)).fetchall()
