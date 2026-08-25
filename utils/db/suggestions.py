"""Databázová vrstva pro komunitní návrhy a hlasování."""

from __future__ import annotations

from typing import Any


STATUSES = {"considering", "accepted", "rejected", "done"}
OPEN_STATUSES = ("open", "considering", "accepted")


def _value(row: Any, key: str, default: Any = None) -> Any:
    try:
        value = row[key]
    except (KeyError, IndexError, TypeError):
        return default
    return default if value is None else value


def get_settings(database: Any, guild_id: int) -> dict[str, Any]:
    with database.connect() as conn:
        row = conn.execute(
            "SELECT channel_id, enabled FROM suggestion_settings WHERE guild_id = ?", (guild_id,)
        ).fetchone()
    return {
        "guild_id": guild_id,
        "channel_id": str(_value(row, "channel_id", "")),
        "enabled": bool(_value(row, "enabled", 0)),
    }


def save_settings(database: Any, guild_id: int, channel_id: int, enabled: bool) -> None:
    excluded = "EXCLUDED" if database.using_postgres else "excluded"
    with database.connect() as conn:
        conn.execute(
            f"""INSERT INTO suggestion_settings (guild_id, channel_id, enabled, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT (guild_id) DO UPDATE SET
                    channel_id = {excluded}.channel_id,
                    enabled = {excluded}.enabled,
                    updated_at = {excluded}.updated_at""",
            (guild_id, channel_id, int(enabled), database.now()),
        )
        conn.commit()


def create_suggestion(
    database: Any, guild_id: int, channel_id: int, author_id: int, title: str, description: str
) -> int:
    values = (guild_id, channel_id, author_id, title, description, database.now(), database.now())
    with database.connect() as conn:
        query = """INSERT INTO suggestions
            (guild_id, channel_id, author_id, title, description, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)"""
        if database.using_postgres:
            row = conn.execute(query + " RETURNING id", values).fetchone()
            suggestion_id = int(row["id"])
        else:
            suggestion_id = int(conn.execute(query, values).lastrowid)
        conn.commit()
    return suggestion_id


def get_suggestion(database: Any, suggestion_id: int):
    with database.connect() as conn:
        return conn.execute("SELECT * FROM suggestions WHERE id = ?", (suggestion_id,)).fetchone()


def get_open_suggestions(database: Any):
    with database.connect() as conn:
        return conn.execute(
            "SELECT * FROM suggestions WHERE status IN ('open', 'considering', 'accepted')"
        ).fetchall()


def get_recent_suggestions(database: Any, guild_id: int, limit: int = 20):
    safe_limit = max(1, min(int(limit), 100))
    with database.connect() as conn:
        return conn.execute(
            """SELECT suggestion.*,
                    COALESCE(SUM(CASE WHEN vote.value = 1 THEN 1 ELSE 0 END), 0) AS upvotes,
                    COALESCE(SUM(CASE WHEN vote.value = -1 THEN 1 ELSE 0 END), 0) AS downvotes
               FROM suggestions AS suggestion
               LEFT JOIN suggestion_votes AS vote ON vote.suggestion_id = suggestion.id
               WHERE suggestion.guild_id = ?
               GROUP BY suggestion.id
               ORDER BY suggestion.id DESC
               LIMIT ?""",
            (guild_id, safe_limit),
        ).fetchall()


def set_message_id(database: Any, suggestion_id: int, message_id: int) -> None:
    with database.connect() as conn:
        conn.execute(
            "UPDATE suggestions SET message_id = ?, updated_at = ? WHERE id = ?",
            (message_id, database.now(), suggestion_id),
        )
        conn.commit()


def get_vote_totals(database: Any, suggestion_id: int) -> tuple[int, int]:
    with database.connect() as conn:
        row = conn.execute(
            """SELECT
                COALESCE(SUM(CASE WHEN value = 1 THEN 1 ELSE 0 END), 0) AS upvotes,
                COALESCE(SUM(CASE WHEN value = -1 THEN 1 ELSE 0 END), 0) AS downvotes
                FROM suggestion_votes WHERE suggestion_id = ?""",
            (suggestion_id,),
        ).fetchone()
    return int(_value(row, "upvotes", 0)), int(_value(row, "downvotes", 0))


def vote(database: Any, suggestion_id: int, user_id: int, value: int) -> tuple[int, int]:
    if value not in (-1, 1):
        raise ValueError("Hlas musí být pro nebo proti.")
    excluded = "EXCLUDED" if database.using_postgres else "excluded"
    with database.connect() as conn:
        conn.execute(
            f"""INSERT INTO suggestion_votes (suggestion_id, user_id, value, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT (suggestion_id, user_id) DO UPDATE SET
                    value = {excluded}.value, created_at = {excluded}.created_at""",
            (suggestion_id, user_id, value, database.now()),
        )
        conn.commit()
    return get_vote_totals(database, suggestion_id)


def set_status(
    database: Any, suggestion_id: int, status: str, moderator_id: int, response: str = ""
) -> None:
    if status not in STATUSES:
        raise ValueError("Neplatný stav návrhu.")
    with database.connect() as conn:
        conn.execute(
            """UPDATE suggestions SET status = ?, moderator_id = ?, moderator_response = ?, updated_at = ?
               WHERE id = ?""",
            (status, moderator_id, response.strip()[:1000], database.now(), suggestion_id),
        )
        conn.commit()
