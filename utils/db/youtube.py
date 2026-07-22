"""Databázové operace YouTube kanálů, odběrů a videí."""

from typing import Any, Optional


def add_channel(database: Any, channel_id: str, name: str, url: str) -> None:
    with database.connect() as conn:
        if database.using_postgres:
            conn.execute("""
                INSERT INTO youtube_channels
                    (youtube_channel_id, youtube_name, youtube_url, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT (youtube_channel_id) DO UPDATE SET
                    youtube_name = EXCLUDED.youtube_name,
                    youtube_url = EXCLUDED.youtube_url
            """, (channel_id, name, url, database.now()))
        else:
            conn.execute("""
                INSERT INTO youtube_channels
                    (youtube_channel_id, youtube_name, youtube_url, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(youtube_channel_id) DO UPDATE SET
                    youtube_name = excluded.youtube_name,
                    youtube_url = excluded.youtube_url
            """, (channel_id, name, url, database.now()))
        conn.commit()


def add_subscription(
    database: Any,
    guild_id: int,
    youtube_channel_id: str,
    discord_channel_id: int,
    mention_role_id: Optional[int] = None,
) -> None:
    excluded = "EXCLUDED" if database.using_postgres else "excluded"
    conflict_target = "(guild_id, youtube_channel_id)"
    with database.connect() as conn:
        conn.execute(f"""
            INSERT INTO subscriptions
                (guild_id, youtube_channel_id, discord_channel_id,
                 mention_role_id, enabled, created_at)
            VALUES (?, ?, ?, ?, 1, ?)
            ON CONFLICT {conflict_target} DO UPDATE SET
                discord_channel_id = {excluded}.discord_channel_id,
                mention_role_id = {excluded}.mention_role_id,
                enabled = 1
        """, (
            guild_id,
            youtube_channel_id,
            discord_channel_id,
            mention_role_id,
            database.now(),
        ))
        conn.commit()


def remove_subscription(database: Any, guild_id: int, channel_id: str) -> bool:
    with database.connect() as conn:
        cursor = conn.execute("""
            DELETE FROM subscriptions
            WHERE guild_id = ? AND youtube_channel_id = ?
        """, (guild_id, channel_id))
        conn.commit()
        return cursor.rowcount > 0


def get_guild_subscriptions(database: Any, guild_id: int):
    with database.connect() as conn:
        return conn.execute("""
            SELECT s.*, y.youtube_name, y.youtube_url
            FROM subscriptions s
            JOIN youtube_channels y
                ON y.youtube_channel_id = s.youtube_channel_id
            WHERE s.guild_id = ?
            ORDER BY y.youtube_name ASC
        """, (guild_id,)).fetchall()


def get_enabled_subscriptions(database: Any):
    with database.connect() as conn:
        return conn.execute("""
            SELECT s.*, y.youtube_name, y.youtube_url
            FROM subscriptions s
            JOIN youtube_channels y
                ON y.youtube_channel_id = s.youtube_channel_id
            WHERE s.enabled = 1
        """).fetchall()


def get_unique_channels(database: Any):
    with database.connect() as conn:
        return conn.execute("""
            SELECT DISTINCT
                y.youtube_channel_id, y.youtube_name, y.youtube_url
            FROM youtube_channels y
            JOIN subscriptions s
                ON s.youtube_channel_id = y.youtube_channel_id
            WHERE s.enabled = 1
        """).fetchall()


def set_last_video(
    database: Any,
    guild_id: int,
    youtube_channel_id: str,
    video_id: str,
) -> None:
    with database.connect() as conn:
        conn.execute("""
            UPDATE subscriptions
            SET last_video_id = ?
            WHERE guild_id = ? AND youtube_channel_id = ?
        """, (video_id, guild_id, youtube_channel_id))
        conn.commit()


def video_exists(database: Any, video_id: str) -> bool:
    with database.connect() as conn:
        return conn.execute(
            "SELECT video_id FROM videos WHERE video_id = ?",
            (video_id,),
        ).fetchone() is not None


def announcement_exists(
    database: Any,
    guild_id: int,
    youtube_channel_id: str,
    video_id: str,
) -> bool:
    with database.connect() as conn:
        return conn.execute("""
            SELECT 1 FROM youtube_announcements
            WHERE guild_id = ? AND youtube_channel_id = ? AND video_id = ?
        """, (guild_id, youtube_channel_id, video_id)).fetchone() is not None


def mark_announced(
    database: Any,
    guild_id: int,
    youtube_channel_id: str,
    video_id: str,
) -> None:
    with database.connect() as conn:
        if database.using_postgres:
            conn.execute("""
                INSERT INTO youtube_announcements
                (guild_id, youtube_channel_id, video_id, announced_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT (guild_id, youtube_channel_id, video_id) DO NOTHING
            """, (guild_id, youtube_channel_id, video_id, database.now()))
        else:
            conn.execute("""
                INSERT OR IGNORE INTO youtube_announcements
                (guild_id, youtube_channel_id, video_id, announced_at)
                VALUES (?, ?, ?, ?)
            """, (guild_id, youtube_channel_id, video_id, database.now()))
        conn.commit()


def add_video(
    database: Any,
    video_id: str,
    youtube_channel_id: str,
    title: str,
    url: str,
    published_at: Optional[str] = None,
) -> None:
    with database.connect() as conn:
        if database.using_postgres:
            conn.execute("""
                INSERT INTO videos (
                    video_id, youtube_channel_id, title, url,
                    published_at, announced_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT (video_id) DO NOTHING
            """, (
                video_id, youtube_channel_id, title, url,
                published_at, database.now(),
            ))
        else:
            conn.execute("""
                INSERT OR IGNORE INTO videos (
                    video_id, youtube_channel_id, title, url,
                    published_at, announced_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                video_id, youtube_channel_id, title, url,
                published_at, database.now(),
            ))
        conn.commit()


def set_subscription_enabled(
    database: Any,
    guild_id: int,
    youtube_channel_id: str,
    enabled: bool,
) -> None:
    with database.connect() as conn:
        conn.execute("""
            UPDATE subscriptions
            SET enabled = ?
            WHERE guild_id = ? AND youtube_channel_id = ?
        """, (int(enabled), guild_id, youtube_channel_id))
        conn.commit()
