"""Nastavení veřejného kola štěstí bez bodů a uživatelských účtů."""

from datetime import datetime, timezone
import re
from typing import Any


MIN_ENTRIES = 2
MAX_ENTRIES = 12
DEFAULT_TITLE = "Kolo štěstí"
DEFAULT_DESCRIPTION = "Zatoč a nech rozhodnout náhodu."
DEFAULT_ENTRIES = (
    {"emoji": "🎉", "label": "Super tah", "color": "#F5B93D", "weight": 1},
    {"emoji": "🍀", "label": "Štěstí", "color": "#45C98B", "weight": 1},
    {"emoji": "🎲", "label": "Náhoda", "color": "#5F6CFF", "weight": 1},
    {"emoji": "✨", "label": "Paráda", "color": "#B967E8", "weight": 1},
    {"emoji": "🔄", "label": "Zkus znovu", "color": "#FF7B52", "weight": 1},
    {"emoji": "😄", "label": "Dobrá volba", "color": "#E85081", "weight": 1},
)
COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


def get_guild_name(database: Any, guild_id: int) -> str | None:
    with database.connect() as conn:
        row = conn.execute(
            "SELECT guild_name FROM guilds WHERE guild_id = ?", (guild_id,)
        ).fetchone()
    return str(row["guild_name"]) if row else None


def _normalize_entry(entry: dict[str, Any]) -> dict[str, Any]:
    emoji = " ".join(str(entry.get("emoji", "")).split())[:32]
    label = " ".join(str(entry.get("label", "")).split())[:48]
    color = str(entry.get("color", "")).strip()
    try:
        weight = int(entry.get("weight", 1))
    except (TypeError, ValueError) as exc:
        raise ValueError("Váha výseče musí být celé číslo.") from exc

    if not emoji or not label or not COLOR_RE.fullmatch(color) or not 1 <= weight <= 100:
        raise ValueError("Každá výseč musí mít emoji, název, barvu #RRGGBB a váhu 1–100.")
    return {"emoji": emoji, "label": label, "color": color.upper(), "weight": weight}


def validate_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized = [_normalize_entry(entry) for entry in entries]
    if not MIN_ENTRIES <= len(normalized) <= MAX_ENTRIES:
        raise ValueError(f"Kolo musí mít {MIN_ENTRIES} až {MAX_ENTRIES} výsečí.")
    return normalized


def parse_entries_text(value: str) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for line in str(value or "").splitlines():
        if not line.strip():
            continue
        parts = [part.strip() for part in line.split("|")]
        if len(parts) != 4:
            raise ValueError("Každý řádek musí mít formát: emoji | název | #barva | váha.")
        entries.append(
            {"emoji": parts[0], "label": parts[1], "color": parts[2], "weight": parts[3]}
        )
    return validate_entries(entries)


def entries_to_text(entries: list[dict[str, Any]]) -> str:
    return "\n".join(
        f"{entry['emoji']} | {entry['label']} | {entry['color']} | {entry['weight']}"
        for entry in entries
    )


def _default_settings(guild_id: int) -> dict[str, Any]:
    entries = [dict(entry) for entry in DEFAULT_ENTRIES]
    return {
        "guild_id": guild_id,
        "title": DEFAULT_TITLE,
        "description": DEFAULT_DESCRIPTION,
        "entries": entries,
        "entries_text": entries_to_text(entries),
    }


def get_settings(database: Any, guild_id: int) -> dict[str, Any]:
    default = _default_settings(guild_id)
    now = datetime.now(timezone.utc).isoformat()
    with database.connect() as conn:
        conn.execute(
            """INSERT INTO lucky_wheel_settings (guild_id, title, description, updated_at)
               VALUES (?, ?, ?, ?) ON CONFLICT (guild_id) DO NOTHING""",
            (guild_id, default["title"], default["description"], now),
        )
        row = conn.execute(
            "SELECT title, description FROM lucky_wheel_settings WHERE guild_id = ?",
            (guild_id,),
        ).fetchone()
        entry_rows = conn.execute(
            """SELECT emoji, label, color, weight FROM lucky_wheel_entries
               WHERE guild_id = ? ORDER BY position ASC""",
            (guild_id,),
        ).fetchall()
        if not entry_rows:
            for position, entry in enumerate(default["entries"]):
                conn.execute(
                    """INSERT INTO lucky_wheel_entries
                       (guild_id, position, emoji, label, color, weight)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (guild_id, position, entry["emoji"], entry["label"], entry["color"], entry["weight"]),
                )
            entry_rows = conn.execute(
                """SELECT emoji, label, color, weight FROM lucky_wheel_entries
                   WHERE guild_id = ? ORDER BY position ASC""",
                (guild_id,),
            ).fetchall()
        conn.commit()

    entries = [dict(entry) for entry in entry_rows]
    return {
        "guild_id": guild_id,
        "title": str(row["title"]),
        "description": str(row["description"]),
        "entries": entries,
        "entries_text": entries_to_text(entries),
    }


def save_settings(
    database: Any, guild_id: int, title: str, description: str, entries: list[dict[str, Any]]
) -> None:
    safe_entries = validate_entries(entries)
    safe_title = " ".join(str(title or "").split())[:80] or DEFAULT_TITLE
    safe_description = " ".join(str(description or "").split())[:240] or DEFAULT_DESCRIPTION
    now = datetime.now(timezone.utc).isoformat()
    with database.connect() as conn:
        excluded = "EXCLUDED" if database.using_postgres else "excluded"
        conn.execute(
            f"""INSERT INTO lucky_wheel_settings (guild_id, title, description, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT (guild_id) DO UPDATE SET
                    title = {excluded}.title,
                    description = {excluded}.description,
                    updated_at = {excluded}.updated_at""",
            (guild_id, safe_title, safe_description, now),
        )
        conn.execute("DELETE FROM lucky_wheel_entries WHERE guild_id = ?", (guild_id,))
        for position, entry in enumerate(safe_entries):
            conn.execute(
                """INSERT INTO lucky_wheel_entries
                   (guild_id, position, emoji, label, color, weight)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (guild_id, position, entry["emoji"], entry["label"], entry["color"], entry["weight"]),
            )
        conn.commit()
