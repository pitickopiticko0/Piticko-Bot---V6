"""Databázové operace ručně ověřovaných ABI ranků."""

from typing import Any, Optional


def get_settings(database: Any, guild_id: int):
    with database.connect() as conn:
        return conn.execute(
            "SELECT * FROM abi_rank_settings WHERE guild_id = ?", (guild_id,)
        ).fetchone()


def save_settings(
    database: Any,
    guild_id: int,
    review_channel_id: int,
    reviewer_role_id: int,
    rank_roles: dict[str, Optional[int]],
    *,
    enabled: bool = True,
) -> None:
    columns = (
        "rookie_role_id", "vanguard_role_id", "elite_role_id",
        "expert_role_id", "master_role_id", "ace_role_id", "hero_role_id",
        "legend_role_id",
    )
    values = [rank_roles.get(name.removesuffix("_role_id")) for name in columns]
    excluded = "EXCLUDED" if database.using_postgres else "excluded"
    with database.connect() as conn:
        conn.execute(f"""
            INSERT INTO abi_rank_settings
                (guild_id, review_channel_id, reviewer_role_id, {", ".join(columns)},
                 enabled, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (guild_id) DO UPDATE SET
                review_channel_id = {excluded}.review_channel_id,
                reviewer_role_id = {excluded}.reviewer_role_id,
                {", ".join(f"{column} = {excluded}.{column}" for column in columns)},
                enabled = {excluded}.enabled,
                updated_at = {excluded}.updated_at
        """, (
            guild_id, review_channel_id, reviewer_role_id, *values,
            int(enabled), database.now(),
        ))
        conn.commit()


def set_enabled(database: Any, guild_id: int, enabled: bool) -> None:
    with database.connect() as conn:
        conn.execute(
            "UPDATE abi_rank_settings SET enabled = ?, updated_at = ? WHERE guild_id = ?",
            (int(enabled), database.now(), guild_id),
        )
        conn.commit()


def get_pending_for_user(database: Any, guild_id: int, user_id: int):
    with database.connect() as conn:
        return conn.execute("""
            SELECT * FROM abi_rank_requests
            WHERE guild_id = ? AND user_id = ? AND status = 'pending'
            ORDER BY id DESC LIMIT 1
        """, (guild_id, user_id)).fetchone()


def create_request(
    database: Any, guild_id: int, user_id: int, game_name: str, game_uid: str,
    rank_key: str, division: Optional[str], screenshot_url: str,
) -> int:
    with database.connect() as conn:
        cursor = conn.execute("""
            INSERT INTO abi_rank_requests
                (guild_id, user_id, game_name, game_uid, rank_key, division,
                 screenshot_url, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?)
        """, (
            guild_id, user_id, game_name, game_uid, rank_key, division,
            screenshot_url, database.now(),
        ))
        if database.using_postgres:
            row = conn.execute(
                "SELECT id FROM abi_rank_requests WHERE guild_id = ? AND user_id = ? "
                "ORDER BY id DESC LIMIT 1", (guild_id, user_id)
            ).fetchone()
            request_id = row["id"]
        else:
            request_id = cursor.lastrowid
        conn.commit()
        return int(request_id)


def set_review_message(database: Any, request_id: int, message_id: int) -> None:
    with database.connect() as conn:
        conn.execute(
            "UPDATE abi_rank_requests SET review_message_id = ? WHERE id = ?",
            (message_id, request_id),
        )
        conn.commit()


def get_by_review_message(database: Any, guild_id: int, message_id: int):
    with database.connect() as conn:
        return conn.execute("""
            SELECT * FROM abi_rank_requests
            WHERE guild_id = ? AND review_message_id = ?
        """, (guild_id, message_id)).fetchone()


def finish(database: Any, request_id: int, status: str, reviewer_id: int,
           reason: Optional[str] = None) -> None:
    with database.connect() as conn:
        conn.execute("""
            UPDATE abi_rank_requests
            SET status = ?, reviewer_id = ?, review_reason = ?, reviewed_at = ?
            WHERE id = ? AND status = 'pending'
        """, (status, reviewer_id, reason, database.now(), request_id))
        conn.commit()


def get_recent(database: Any, guild_id: int, limit: int = 20):
    with database.connect() as conn:
        return conn.execute("""
            SELECT * FROM abi_rank_requests
            WHERE guild_id = ? ORDER BY id DESC LIMIT ?
        """, (guild_id, limit)).fetchall()


def get_leaderboard(database: Any, guild_id: int, limit: int = 20):
    with database.connect() as conn:
        return conn.execute("""
            SELECT * FROM abi_rank_requests
            WHERE guild_id = ? AND status = 'approved'
              AND id IN (
                SELECT MAX(id) FROM abi_rank_requests
                WHERE guild_id = ? AND status = 'approved' GROUP BY user_id
              )
            ORDER BY CASE rank_key
                WHEN 'legend' THEN 8 WHEN 'hero' THEN 7 WHEN 'ace' THEN 6
                WHEN 'master' THEN 5 WHEN 'expert' THEN 4 WHEN 'elite' THEN 3
                WHEN 'vanguard' THEN 2 ELSE 1 END DESC, reviewed_at ASC
            LIMIT ?
        """, (guild_id, guild_id, limit)).fetchall()
