"""Ukládání plánovaných Discord oznámení."""

from __future__ import annotations

from typing import Any


def create(
    database: Any,
    guild_id: int,
    channel_id: int,
    author_id: int,
    title: str,
    content: str,
    color: str,
    scheduled_at: str,
) -> int:
    values = (
        guild_id,
        channel_id,
        author_id,
        title.strip()[:256],
        content.strip()[:4000],
        color.strip()[:7],
        scheduled_at,
        database.now(),
    )
    query = """INSERT INTO scheduled_announcements
        (guild_id, channel_id, author_id, title, content, color, scheduled_at, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)"""
    with database.connect() as conn:
        if database.using_postgres:
            row = conn.execute(query + " RETURNING id", values).fetchone()
            announcement_id = int(row["id"])
        else:
            announcement_id = int(conn.execute(query, values).lastrowid)
        conn.commit()
    return announcement_id


def list_for_guild(database: Any, guild_id: int, limit: int = 50):
    safe_limit = max(1, min(int(limit), 100))
    with database.connect() as conn:
        return conn.execute(
            """SELECT * FROM scheduled_announcements
               WHERE guild_id = ?
               ORDER BY CASE status WHEN 'scheduled' THEN 0 WHEN 'sent' THEN 1 ELSE 2 END,
                        scheduled_at ASC
               LIMIT ?""",
            (guild_id, safe_limit),
        ).fetchall()


def get_for_guild(database: Any, announcement_id: int, guild_id: int):
    with database.connect() as conn:
        return conn.execute(
            "SELECT * FROM scheduled_announcements WHERE id = ? AND guild_id = ?",
            (announcement_id, guild_id),
        ).fetchone()


def list_due(database: Any, now: str, limit: int = 25):
    safe_limit = max(1, min(int(limit), 100))
    with database.connect() as conn:
        return conn.execute(
            """SELECT * FROM scheduled_announcements
               WHERE status = 'scheduled' AND scheduled_at <= ?
               ORDER BY scheduled_at, id
               LIMIT ?""",
            (now, safe_limit),
        ).fetchall()


def update(
    database: Any,
    announcement_id: int,
    guild_id: int,
    channel_id: int,
    title: str,
    content: str,
    color: str,
    scheduled_at: str,
) -> bool:
    with database.connect() as conn:
        cursor = conn.execute(
            """UPDATE scheduled_announcements
               SET channel_id = ?, title = ?, content = ?, color = ?, scheduled_at = ?
               WHERE id = ? AND guild_id = ? AND status = 'scheduled'""",
            (
                channel_id, title.strip()[:256], content.strip()[:4000], color.strip()[:7],
                scheduled_at, announcement_id, guild_id,
            ),
        )
        conn.commit()
    return bool(cursor.rowcount)


def cancel(database: Any, announcement_id: int, guild_id: int) -> bool:
    with database.connect() as conn:
        cursor = conn.execute(
            """UPDATE scheduled_announcements
               SET status = 'cancelled', cancelled_at = ?
               WHERE id = ? AND guild_id = ? AND status = 'scheduled'""",
            (database.now(), announcement_id, guild_id),
        )
        conn.commit()
    return bool(cursor.rowcount)


def mark_sent(database: Any, announcement_id: int, message_id: int) -> None:
    with database.connect() as conn:
        conn.execute(
            """UPDATE scheduled_announcements
               SET status = 'sent', message_id = ?, sent_at = ?
               WHERE id = ? AND status = 'scheduled'""",
            (message_id, database.now(), announcement_id),
        )
        conn.commit()


def mark_failed(database: Any, announcement_id: int) -> None:
    with database.connect() as conn:
        conn.execute(
            """UPDATE scheduled_announcements
               SET status = 'failed'
               WHERE id = ? AND status = 'scheduled'""",
            (announcement_id,),
        )
        conn.commit()
