"""Databázová vrstva veřejného kola štěstí.

Výsledek se vždy zapisuje atomicky. Samotné tlačítko v prohlížeči tedy
nemůže obejít limit jednoho zatočení za 24 hodin.
"""

from datetime import datetime, timedelta, timezone
from typing import Any


COOLDOWN = timedelta(hours=24)


def get_guild_name(database: Any, guild_id: int) -> str | None:
    with database.connect() as conn:
        row = conn.execute(
            "SELECT guild_name FROM guilds WHERE guild_id = ?", (guild_id,)
        ).fetchone()
    return str(row["guild_name"]) if row else None


def get_player(database: Any, guild_id: int, user_id: int):
    with database.connect() as conn:
        return conn.execute(
            """SELECT guild_id, user_id, points, spins, last_spin_at, updated_at
               FROM lucky_wheel_players
               WHERE guild_id = ? AND user_id = ?""",
            (guild_id, user_id),
        ).fetchone()


def spin(database: Any, guild_id: int, user_id: int, points: int, display_name: str):
    """Přidá body, pouze pokud hráč netočil během posledních 24 hodin.

    Vrací dvojici ``(provedeno, hráč)``. Kontrola i zápis probíhají v jednom
    SQL příkazu, takže dvojí rychlé kliknutí neudělí odměnu dvakrát.
    """
    awarded_points = max(0, min(int(points), 500))
    safe_name = " ".join(str(display_name).split())[:80] or "Discord uživatel"
    now = datetime.now(timezone.utc)
    now_value = now.isoformat()
    allowed_before = (now - COOLDOWN).isoformat()

    with database.connect() as conn:
        excluded = "EXCLUDED" if database.using_postgres else "excluded"
        cursor = conn.execute(
                f"""INSERT INTO lucky_wheel_players
                    (guild_id, user_id, display_name, points, spins, last_spin_at, updated_at)
                VALUES (?, ?, ?, ?, 1, ?, ?)
                ON CONFLICT (guild_id, user_id) DO UPDATE SET
                    display_name = {excluded}.display_name,
                    points = lucky_wheel_players.points + {excluded}.points,
                    spins = lucky_wheel_players.spins + 1,
                    last_spin_at = {excluded}.last_spin_at,
                    updated_at = {excluded}.updated_at
                WHERE lucky_wheel_players.last_spin_at <= ?""",
            (
                guild_id,
                user_id,
                safe_name,
                awarded_points,
                now_value,
                now_value,
                allowed_before,
            ),
        )
        applied = cursor.rowcount > 0
        player = conn.execute(
            """SELECT guild_id, user_id, points, spins, last_spin_at, updated_at
               FROM lucky_wheel_players
               WHERE guild_id = ? AND user_id = ?""",
            (guild_id, user_id),
        ).fetchone()
        conn.commit()

    return applied, player


def leaderboard(database: Any, guild_id: int, limit: int = 10):
    safe_limit = max(1, min(int(limit), 20))
    with database.connect() as conn:
        return conn.execute(
            """SELECT user_id, display_name, points, spins
               FROM lucky_wheel_players
               WHERE guild_id = ?
               ORDER BY points DESC, spins DESC, updated_at ASC
               LIMIT ?""",
            (guild_id, safe_limit),
        ).fetchall()
