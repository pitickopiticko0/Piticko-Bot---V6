"""Dashboard adapter nad stejnou databází, kterou používá Discord bot.

Welcome a YouTube nastavení se čtou a ukládají přes utils.database.db,
takže změny ze slash příkazů i dashboardu používají stejné tabulky.
"""

from __future__ import annotations

import asyncio
from typing import Any

from utils.database import db


DEFAULT_SETTINGS: dict[str, Any] = {
    "general": {
        "language": "cs",
        "timezone": "Europe/Prague",
        "command_channel_id": "",
    },
    "welcome": {
        "enabled": False,
        "channel_id": "",
        "message": "Vítej {mention} na serveru {server}!",
        "embed_title": "Vítej!",
        "embed_color": "#5865F2",
        "dm_enabled": False,
    },
    "youtube": {
        "enabled": False,
        "channel_id": "",
        "youtube_channel_id": "",
        "custom_message": "📺 Nové video: {title}\n{url}",
        "mention_role_id": "",
        "check_interval": 300,
    },
}


def _value(row: Any, key: str, default: Any = None) -> Any:
    if row is None:
        return default
    try:
        value = row[key]
    except (KeyError, IndexError, TypeError):
        value = getattr(row, key, default)
    return default if value is None else value


class DashboardStorage:
    """Zachovává původní async rozhraní dashboardu, ale používá bot DB."""

    def __init__(self) -> None:
        self.backend_name = "postgresql" if db.using_postgres else "sqlite"

    async def initialize(self) -> None:
        # utils.database.db inicializuje tabulky už při importu.
        return None

    async def get_settings(self, guild_id: str) -> dict[str, Any]:
        return await asyncio.to_thread(self._get_settings_sync, int(guild_id))

    def _get_settings_sync(self, guild_id: int) -> dict[str, Any]:
        settings = {
            "general": dict(DEFAULT_SETTINGS["general"]),
            "welcome": dict(DEFAULT_SETTINGS["welcome"]),
            "youtube": dict(DEFAULT_SETTINGS["youtube"]),
        }

        welcome = db.get_welcome_settings(guild_id)
        if welcome is not None:
            settings["welcome"].update(
                {
                    "enabled": bool(_value(welcome, "enabled", 0)),
                    "channel_id": str(_value(welcome, "channel_id", "")),
                    "message": str(
                        _value(
                            welcome,
                            "message",
                            DEFAULT_SETTINGS["welcome"]["message"],
                        )
                    ),
                }
            )

        subscriptions = list(db.get_guild_subscriptions(guild_id))
        if subscriptions:
            # Současný dashboardový formulář umí jeden YouTube kanál.
            # Proto se zde zobrazuje první uložené předplatné.
            subscription = subscriptions[0]
            settings["youtube"].update(
                {
                    "enabled": bool(_value(subscription, "enabled", 0)),
                    "channel_id": str(
                        _value(subscription, "discord_channel_id", "")
                    ),
                    "youtube_channel_id": str(
                        _value(subscription, "youtube_channel_id", "")
                    ),
                    "mention_role_id": str(
                        _value(subscription, "mention_role_id", "")
                    ),
                }
            )

        return settings

    async def update_module(
        self,
        guild_id: str,
        module: str,
        values: dict[str, Any],
    ) -> None:
        guild_id_int = int(guild_id)

        if module == "welcome":
            await asyncio.to_thread(
                self._save_welcome_sync,
                guild_id_int,
                values,
            )
            return

        if module == "youtube":
            await asyncio.to_thread(
                self._save_youtube_sync,
                guild_id_int,
                values,
            )
            return

        # General nastavení zatím bot ve své DB nemá a slash příkazy je nepoužívají.
        # Proto se zatím pouze přijme bez zápisu. Pro jeho synchronizaci je potřeba
        # nejdřív přidat samostatnou tabulku a metody do utils/database.py.
        if module == "general":
            return

        raise ValueError(f"Neznámý dashboard modul: {module}")

    def _save_welcome_sync(self, guild_id: int, values: dict[str, Any]) -> None:
        enabled = bool(values.get("enabled"))
        channel_raw = str(values.get("channel_id", "")).strip()
        message = str(values.get("message", "")).strip()

        existing = db.get_welcome_settings(guild_id)

        if enabled:
            if not channel_raw.isdigit():
                raise ValueError("Welcome kanál musí obsahovat platné Discord ID.")

            role_id = _value(existing, "role_id", None)
            db.set_welcome_settings(
                guild_id=guild_id,
                channel_id=int(channel_raw),
                role_id=int(role_id) if role_id else None,
                message=message or DEFAULT_SETTINGS["welcome"]["message"],
            )
        elif existing is not None:
            db.disable_welcome(guild_id)

    def _save_youtube_sync(self, guild_id: int, values: dict[str, Any]) -> None:
        enabled = bool(values.get("enabled"))
        youtube_channel_id = str(values.get("youtube_channel_id", "")).strip()
        discord_channel_raw = str(values.get("channel_id", "")).strip()
        mention_role_raw = str(values.get("mention_role_id", "")).strip()

        if enabled:
            if not youtube_channel_id:
                raise ValueError("Chybí YouTube Channel ID.")
            if not discord_channel_raw.isdigit():
                raise ValueError("Cílový Discord kanál musí obsahovat platné ID.")
            if mention_role_raw and not mention_role_raw.isdigit():
                raise ValueError("Role musí obsahovat platné Discord ID.")

            # Formulář nyní neposílá název kanálu, proto se jako dočasný název
            # použije Channel ID. URL je přesto platná a bot ji může sledovat.
            db.add_youtube_channel(
                channel_id=youtube_channel_id,
                name=youtube_channel_id,
                url=f"https://www.youtube.com/channel/{youtube_channel_id}",
            )
            db.add_subscription(
                guild_id=guild_id,
                youtube_channel_id=youtube_channel_id,
                discord_channel_id=int(discord_channel_raw),
                mention_role_id=(
                    int(mention_role_raw) if mention_role_raw else None
                ),
            )
            return

        subscriptions = list(db.get_guild_subscriptions(guild_id))
        for subscription in subscriptions:
            current_channel_id = str(
                _value(subscription, "youtube_channel_id", "")
            )
            if not youtube_channel_id or current_channel_id == youtube_channel_id:
                db.pause_subscription(guild_id, current_channel_id)

    async def count_configured_guilds(self, guild_ids: list[str]) -> int:
        return await asyncio.to_thread(self._count_configured_sync, guild_ids)

    def _count_configured_sync(self, guild_ids: list[str]) -> int:
        total = 0
        for guild_id in guild_ids:
            guild_id_int = int(guild_id)
            if db.get_welcome_settings(guild_id_int) is not None:
                total += 1
                continue
            if db.get_guild_subscriptions(guild_id_int):
                total += 1
        return total
