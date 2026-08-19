"""Databázové operace pro komunitní počítání oveček."""

from typing import Any


def get_settings(database: Any, guild_id: int):
    with database.connect() as conn:
        return conn.execute(
            "SELECT * FROM sheep_game_settings WHERE guild_id = ?", (guild_id,)
        ).fetchone()


def save_settings(
    database: Any, guild_id: int, channel_id: int | None, enabled: bool
) -> None:
    with database.connect() as conn:
        excluded = "EXCLUDED" if database.using_postgres else "excluded"
        conn.execute(
            f"""INSERT INTO sheep_game_settings
                (guild_id, channel_id, enabled, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT (guild_id) DO UPDATE SET
                    channel_id = {excluded}.channel_id,
                    enabled = {excluded}.enabled,
                    updated_at = {excluded}.updated_at""",
            (guild_id, channel_id, int(enabled), database.now()),
        )
        conn.commit()


def record_valid_count(database: Any, guild_id: int, user_id: int, number: int) -> None:
    with database.connect() as conn:
        excluded = "EXCLUDED" if database.using_postgres else "excluded"
        conn.execute(
            """UPDATE sheep_game_settings SET
                current_count = ?,
                record_count = CASE WHEN record_count < ? THEN ? ELSE record_count END,
                last_user_id = ?, total_valid_counts = total_valid_counts + 1,
                updated_at = ?
                WHERE guild_id = ?""",
            (number, number, number, user_id, database.now(), guild_id),
        )
        conn.execute(
            f"""INSERT INTO sheep_game_players
                (guild_id, user_id, valid_counts, chains_broken, updated_at)
                VALUES (?, ?, 1, 0, ?)
                ON CONFLICT (guild_id, user_id) DO UPDATE SET
                    valid_counts = sheep_game_players.valid_counts + 1,
                    updated_at = {excluded}.updated_at""",
            (guild_id, user_id, database.now()),
        )
        conn.commit()


def break_chain(database: Any, guild_id: int, user_id: int) -> int:
    with database.connect() as conn:
        row = conn.execute(
            "SELECT current_count FROM sheep_game_settings WHERE guild_id = ?",
            (guild_id,),
        ).fetchone()
        previous = int(row["current_count"]) if row else 0
        conn.execute(
            """UPDATE sheep_game_settings SET current_count = 0,
                last_user_id = NULL, updated_at = ? WHERE guild_id = ?""",
            (database.now(), guild_id),
        )
        excluded = "EXCLUDED" if database.using_postgres else "excluded"
        conn.execute(
            f"""INSERT INTO sheep_game_players
                (guild_id, user_id, valid_counts, chains_broken, updated_at)
                VALUES (?, ?, 0, 1, ?)
                ON CONFLICT (guild_id, user_id) DO UPDATE SET
                    chains_broken = sheep_game_players.chains_broken + 1,
                    updated_at = {excluded}.updated_at""",
            (guild_id, user_id, database.now()),
        )
        conn.commit()
        return previous


def reset_chain(database: Any, guild_id: int) -> None:
    with database.connect() as conn:
        conn.execute(
            """UPDATE sheep_game_settings SET current_count = 0,
                last_user_id = NULL, updated_at = ? WHERE guild_id = ?""",
            (database.now(), guild_id),
        )
        conn.commit()


def get_leaderboard(database: Any, guild_id: int, limit: int = 10):
    safe_limit = max(1, min(int(limit), 25))
    with database.connect() as conn:
        return conn.execute(
            """SELECT * FROM sheep_game_players WHERE guild_id = ?
                ORDER BY valid_counts DESC, chains_broken ASC, user_id ASC LIMIT ?""",
            (guild_id, safe_limit),
        ).fetchall()
