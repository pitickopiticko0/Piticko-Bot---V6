from typing import Optional

from utils.database import db


class TwitchStore:
    def __init__(self) -> None:
        self._init_table()

    def _init_table(self) -> None:
        id_column = "BIGSERIAL PRIMARY KEY" if db.using_postgres else "INTEGER PRIMARY KEY AUTOINCREMENT"
        integer_type = "BIGINT" if db.using_postgres else "INTEGER"
        with db.connect() as conn:
            conn.execute(f"""
                CREATE TABLE IF NOT EXISTS twitch_subscriptions (
                    id {id_column},
                    guild_id {integer_type} NOT NULL,
                    twitch_user_id TEXT NOT NULL,
                    streamer_login TEXT NOT NULL,
                    streamer_name TEXT NOT NULL,
                    discord_channel_id {integer_type} NOT NULL,
                    mention_role_id {integer_type},
                    profile_image_url TEXT,
                    last_stream_id TEXT,
                    is_live INTEGER NOT NULL DEFAULT 0,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    UNIQUE(guild_id, twitch_user_id)
                )
            """)
            conn.commit()

    def add_subscription(self, guild_id: int, twitch_user_id: str, streamer_login: str,
                         streamer_name: str, discord_channel_id: int,
                         mention_role_id: Optional[int], profile_image_url: Optional[str]) -> None:
        with db.connect() as conn:
            if db.using_postgres:
                conn.execute("""
                    INSERT INTO twitch_subscriptions (
                        guild_id, twitch_user_id, streamer_login, streamer_name,
                        discord_channel_id, mention_role_id, profile_image_url,
                        enabled, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)
                    ON CONFLICT (guild_id, twitch_user_id) DO UPDATE SET
                        streamer_login = EXCLUDED.streamer_login,
                        streamer_name = EXCLUDED.streamer_name,
                        discord_channel_id = EXCLUDED.discord_channel_id,
                        mention_role_id = EXCLUDED.mention_role_id,
                        profile_image_url = EXCLUDED.profile_image_url,
                        enabled = 1
                """, (guild_id, twitch_user_id, streamer_login, streamer_name,
                      discord_channel_id, mention_role_id, profile_image_url, db.now()))
            else:
                row = conn.execute("""
                    SELECT created_at, last_stream_id, is_live
                    FROM twitch_subscriptions
                    WHERE guild_id = ? AND twitch_user_id = ?
                """, (guild_id, twitch_user_id)).fetchone()
                created_at = row["created_at"] if row else db.now()
                last_stream_id = row["last_stream_id"] if row else None
                is_live = row["is_live"] if row else 0
                conn.execute("""
                    INSERT OR REPLACE INTO twitch_subscriptions (
                        guild_id, twitch_user_id, streamer_login, streamer_name,
                        discord_channel_id, mention_role_id, profile_image_url,
                        last_stream_id, is_live, enabled, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
                """, (guild_id, twitch_user_id, streamer_login, streamer_name,
                      discord_channel_id, mention_role_id, profile_image_url,
                      last_stream_id, is_live, created_at))
            conn.commit()

    def remove_subscription(self, guild_id: int, streamer_login: str) -> bool:
        with db.connect() as conn:
            cur = conn.execute("""
                DELETE FROM twitch_subscriptions
                WHERE guild_id = ? AND LOWER(streamer_login) = LOWER(?)
            """, (guild_id, streamer_login))
            conn.commit()
            return cur.rowcount > 0

    def get_guild_subscriptions(self, guild_id: int):
        with db.connect() as conn:
            return conn.execute("""
                SELECT * FROM twitch_subscriptions
                WHERE guild_id = ? ORDER BY streamer_name ASC
            """, (guild_id,)).fetchall()

    def get_enabled_subscriptions(self):
        with db.connect() as conn:
            return conn.execute("""
                SELECT * FROM twitch_subscriptions
                WHERE enabled = 1 ORDER BY streamer_login ASC
            """).fetchall()

    def set_stream_state(self, guild_id: int, twitch_user_id: str,
                         stream_id: Optional[str], is_live: bool) -> None:
        with db.connect() as conn:
            conn.execute("""
                UPDATE twitch_subscriptions
                SET last_stream_id = ?, is_live = ?
                WHERE guild_id = ? AND twitch_user_id = ?
            """, (stream_id, 1 if is_live else 0, guild_id, twitch_user_id))
            conn.commit()


twitch_store = TwitchStore()
