"""Uložení nastavení a mapování reakcí na Discord role."""

from __future__ import annotations

from typing import Any


MAX_REACTION_ROLES = 8
DEFAULT_TITLE = "Vyber si role"
DEFAULT_DESCRIPTION = "Klikni na reakci pod touto zprávou a roli ti přidám. Odebráním reakce se role zase odebere."


def _value(row: Any, key: str, default: Any = None) -> Any:
    try:
        value = row[key]
    except (KeyError, IndexError, TypeError):
        return default
    return default if value is None else value


def normalize_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Odstraní prázdné řádky a ověří emoji i Discord ID role."""
    result: list[dict[str, Any]] = []
    used_emojis: set[str] = set()
    used_roles: set[int] = set()

    for raw_entry in entries:
        emoji = " ".join(str(raw_entry.get("emoji", "")).split())[:100]
        role_raw = str(raw_entry.get("role_id", "")).strip()
        if not emoji and not role_raw:
            continue
        if not emoji or not role_raw.isdigit():
            raise ValueError("Každý řádek reakční role potřebuje emoji a platnou Discord roli.")
        role_id = int(role_raw)
        if emoji in used_emojis:
            raise ValueError("Stejné emoji můžeš v jednom panelu použít jen jednou.")
        if role_id in used_roles:
            raise ValueError("Stejnou roli můžeš v jednom panelu použít jen jednou.")
        used_emojis.add(emoji)
        used_roles.add(role_id)
        result.append({"emoji": emoji, "role_id": role_id})

    if not result:
        raise ValueError("Přidej alespoň jednu reakční roli.")
    if len(result) > MAX_REACTION_ROLES:
        raise ValueError(f"Panel může mít nejvýše {MAX_REACTION_ROLES} reakcí.")
    return result


def get_settings(database: Any, guild_id: int) -> dict[str, Any]:
    with database.connect() as conn:
        row = conn.execute(
            """SELECT guild_id, channel_id, message_id, title, description, enabled
               FROM reaction_role_settings WHERE guild_id = ?""",
            (guild_id,),
        ).fetchone()
        entries = conn.execute(
            """SELECT emoji, role_id FROM reaction_role_entries
               WHERE guild_id = ? ORDER BY position ASC""",
            (guild_id,),
        ).fetchall()

    return {
        "guild_id": guild_id,
        "channel_id": str(_value(row, "channel_id", "")),
        "message_id": str(_value(row, "message_id", "")),
        "title": str(_value(row, "title", DEFAULT_TITLE)),
        "description": str(_value(row, "description", DEFAULT_DESCRIPTION)),
        "enabled": bool(_value(row, "enabled", 0)),
        "entries": [
            {"emoji": str(_value(entry, "emoji", "")), "role_id": str(_value(entry, "role_id", ""))}
            for entry in entries
        ],
    }


def save_settings(
    database: Any,
    guild_id: int,
    channel_id: int,
    title: str,
    description: str,
    entries: list[dict[str, Any]],
    *,
    enabled: bool,
) -> None:
    safe_entries = normalize_entries(entries)
    safe_title = " ".join(str(title or "").split())[:120] or DEFAULT_TITLE
    safe_description = str(description or "").strip()[:1800] or DEFAULT_DESCRIPTION
    excluded = "EXCLUDED" if database.using_postgres else "excluded"

    with database.connect() as conn:
        conn.execute(
            f"""INSERT INTO reaction_role_settings
                   (guild_id, channel_id, message_id, title, description, enabled, updated_at)
               VALUES (?, ?, NULL, ?, ?, ?, ?)
               ON CONFLICT (guild_id) DO UPDATE SET
                   channel_id = {excluded}.channel_id,
                   message_id = NULL,
                   title = {excluded}.title,
                   description = {excluded}.description,
                   enabled = {excluded}.enabled,
                   updated_at = {excluded}.updated_at""",
            (guild_id, channel_id, safe_title, safe_description, int(enabled), database.now()),
        )
        conn.execute("DELETE FROM reaction_role_entries WHERE guild_id = ?", (guild_id,))
        for position, entry in enumerate(safe_entries):
            conn.execute(
                """INSERT INTO reaction_role_entries (guild_id, position, emoji, role_id)
                   VALUES (?, ?, ?, ?)""",
                (guild_id, position, entry["emoji"], entry["role_id"]),
            )
        conn.commit()


def set_message_id(database: Any, guild_id: int, message_id: int) -> None:
    with database.connect() as conn:
        conn.execute(
            """UPDATE reaction_role_settings
               SET message_id = ?, updated_at = ?
               WHERE guild_id = ?""",
            (message_id, database.now(), guild_id),
        )
        conn.commit()


def get_mapping(database: Any, guild_id: int, message_id: int, emoji: str):
    with database.connect() as conn:
        row = conn.execute(
            """SELECT entry.role_id
               FROM reaction_role_settings AS settings
               JOIN reaction_role_entries AS entry ON entry.guild_id = settings.guild_id
               WHERE settings.guild_id = ?
                 AND settings.message_id = ?
                 AND settings.enabled = 1
                 AND entry.emoji = ?""",
            (guild_id, message_id, emoji),
        ).fetchone()
    return int(_value(row, "role_id")) if row is not None else None
