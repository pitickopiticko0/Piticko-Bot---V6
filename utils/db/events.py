"""Databázová vrstva kalendáře komunitních akcí."""

from __future__ import annotations

from typing import Any


def create(database: Any, guild_id: int, channel_id: int, host_id: int, title: str, description: str, event_at: str) -> int:
    values = (guild_id, channel_id, host_id, title.strip()[:200], description.strip()[:2000], event_at, database.now())
    query = """INSERT INTO community_events
        (guild_id, channel_id, host_id, title, description, event_at, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)"""
    with database.connect() as conn:
        if database.using_postgres:
            row = conn.execute(query + " RETURNING id", values).fetchone()
            event_id = int(row["id"])
        else:
            event_id = int(conn.execute(query, values).lastrowid)
        conn.commit()
    return event_id


def get(database: Any, event_id: int, guild_id: int | None = None):
    query = "SELECT * FROM community_events WHERE id = ?"
    values: tuple = (event_id,)
    if guild_id is not None:
        query += " AND guild_id = ?"
        values = (event_id, guild_id)
    with database.connect() as conn:
        return conn.execute(query, values).fetchone()


def list_for_guild(database: Any, guild_id: int, limit: int = 30):
    with database.connect() as conn:
        return conn.execute(
            """SELECT event.*, COUNT(participant.user_id) AS participant_count
               FROM community_events AS event
               LEFT JOIN community_event_participants AS participant ON participant.event_id = event.id
               WHERE event.guild_id = ?
               GROUP BY event.id
               ORDER BY CASE event.status WHEN 'pending' THEN 0 WHEN 'active' THEN 1 ELSE 2 END,
                        event.event_at ASC
               LIMIT ?""",
            (guild_id, max(1, min(int(limit), 100))),
        ).fetchall()


def list_pending(database: Any):
    with database.connect() as conn:
        return conn.execute("SELECT * FROM community_events WHERE status = 'pending' ORDER BY id").fetchall()


def list_active(database: Any):
    with database.connect() as conn:
        return conn.execute("SELECT * FROM community_events WHERE status = 'active' AND message_id IS NOT NULL").fetchall()


def set_published(database: Any, event_id: int, message_id: int) -> None:
    with database.connect() as conn:
        conn.execute(
            """UPDATE community_events SET status = 'active', message_id = ?, published_at = ?
               WHERE id = ? AND status = 'pending'""",
            (message_id, database.now(), event_id),
        )
        conn.commit()


def cancel(database: Any, event_id: int, guild_id: int) -> bool:
    with database.connect() as conn:
        cursor = conn.execute(
            """UPDATE community_events SET status = 'cancelled', cancelled_at = ?
               WHERE id = ? AND guild_id = ? AND status IN ('pending', 'active')""",
            (database.now(), event_id, guild_id),
        )
        conn.commit()
    return bool(cursor.rowcount)


def join(database: Any, event_id: int, user_id: int) -> bool:
    with database.connect() as conn:
        if database.using_postgres:
            cursor = conn.execute(
                """INSERT INTO community_event_participants (event_id, user_id, joined_at)
                   VALUES (?, ?, ?) ON CONFLICT (event_id, user_id) DO NOTHING""",
                (event_id, user_id, database.now()),
            )
        else:
            cursor = conn.execute(
                """INSERT OR IGNORE INTO community_event_participants (event_id, user_id, joined_at)
                   VALUES (?, ?, ?)""",
                (event_id, user_id, database.now()),
            )
        conn.commit()
    return bool(cursor.rowcount)


def count_participants(database: Any, event_id: int) -> int:
    with database.connect() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS total FROM community_event_participants WHERE event_id = ?", (event_id,)
        ).fetchone()
    return int(row["total"])

