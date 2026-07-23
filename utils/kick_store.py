from typing import Optional

from utils.database import db


def add(guild_id: int, user_id: str, slug: str, channel_id: int, role_id: Optional[int]) -> None:
    with db.connect() as conn:
        excluded = "EXCLUDED" if db.using_postgres else "excluded"
        conn.execute(f"""
            INSERT INTO kick_subscriptions
            (guild_id, kick_user_id, streamer_slug, discord_channel_id,
             mention_role_id, is_live, enabled, created_at)
            VALUES (?, ?, ?, ?, ?, 0, 1, ?)
            ON CONFLICT (guild_id, kick_user_id) DO UPDATE SET
                streamer_slug = {excluded}.streamer_slug,
                discord_channel_id = {excluded}.discord_channel_id,
                mention_role_id = {excluded}.mention_role_id,
                enabled = 1
        """, (guild_id, user_id, slug, channel_id, role_id, db.now()))
        conn.commit()


def remove(guild_id: int, slug: str) -> bool:
    with db.connect() as conn:
        cur = conn.execute(
            "DELETE FROM kick_subscriptions WHERE guild_id = ? AND LOWER(streamer_slug) = LOWER(?)",
            (guild_id, slug),
        )
        conn.commit()
        return cur.rowcount > 0


def get_guild(guild_id: int):
    with db.connect() as conn:
        return conn.execute(
            "SELECT * FROM kick_subscriptions WHERE guild_id = ? ORDER BY streamer_slug",
            (guild_id,),
        ).fetchall()


def get_enabled():
    with db.connect() as conn:
        return conn.execute(
            "SELECT * FROM kick_subscriptions WHERE enabled = 1 ORDER BY streamer_slug"
        ).fetchall()


def set_live(guild_id: int, user_id: str, live: bool) -> None:
    with db.connect() as conn:
        conn.execute(
            "UPDATE kick_subscriptions SET is_live = ? WHERE guild_id = ? AND kick_user_id = ?",
            (int(live), guild_id, user_id),
        )
        conn.commit()
