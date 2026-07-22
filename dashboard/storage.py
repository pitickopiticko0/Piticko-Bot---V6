"""Dashboard adapter používající stejnou databázi jako Discord bot.

Soubor zachovává původní async rozhraní dashboardu, takže dashboard/app.py
není potřeba měnit. Všechna nastavení se ukládají přes utils.database.db.
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
    "autorole": {
        "enabled": False,
        "role_id": "",
    },
    "modlogs": {
        "enabled": False,
        "channel_id": "",
        "log_members": True,
        "log_messages": True,
        "log_voice": True,
        "log_channels": True,
        "log_bans": True,
    },
    "antispam": {
        "enabled": False,
        "max_messages": 6,
        "interval_seconds": 8,
        "duplicate_limit": 3,
        "mention_limit": 5,
        "timeout_minutes": 10,
        "delete_messages": True,
    },
    "tickets": {
        "enabled": False,
        "panel_channel_id": "",
        "category_id": "",
        "support_role_id": "",
        "log_channel_id": "",
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


def _discord_id(value: Any, *, field: str, required: bool = False) -> int | None:
    raw = str(value or "").strip()
    if not raw:
        if required:
            raise ValueError(f"{field} je povinné.")
        return None
    if not raw.isdigit():
        raise ValueError(f"{field} musí obsahovat platné Discord ID.")
    return int(raw)


class DashboardStorage:
    def __init__(self) -> None:
        self.backend_name = "postgresql" if db.using_postgres else "sqlite"

    async def initialize(self) -> None:
        # utils.database.db vytvoří a migruje tabulky při importu.
        return None

    async def get_settings(self, guild_id: str) -> dict[str, Any]:
        return await asyncio.to_thread(self._get_settings_sync, int(guild_id))

    def _get_settings_sync(self, guild_id: int) -> dict[str, Any]:
        settings = {
            module: dict(values)
            for module, values in DEFAULT_SETTINGS.items()
        }

        general = db.get_guild_settings(guild_id)
        if general is not None:
            settings["general"].update({
                "language": str(_value(general, "language", "cs")),
                "timezone": str(_value(general, "timezone", "Europe/Prague")),
                "command_channel_id": str(_value(general, "command_channel_id", "")),
            })

        welcome = db.get_welcome_settings(guild_id)
        if welcome is not None:
            settings["welcome"].update({
                "enabled": bool(_value(welcome, "enabled", 0)),
                "channel_id": str(_value(welcome, "channel_id", "")),
                "message": str(_value(welcome, "message", DEFAULT_SETTINGS["welcome"]["message"])),
                "embed_title": str(_value(welcome, "embed_title", "Vítej!")),
                "embed_color": str(_value(welcome, "embed_color", "#5865F2")),
                "dm_enabled": bool(_value(welcome, "dm_enabled", 0)),
            })

        subscriptions = list(db.get_guild_subscriptions(guild_id))
        if subscriptions:
            subscription = subscriptions[0]
            settings["youtube"].update({
                "enabled": bool(_value(subscription, "enabled", 0)),
                "channel_id": str(_value(subscription, "discord_channel_id", "")),
                "youtube_channel_id": str(_value(subscription, "youtube_channel_id", "")),
                "custom_message": str(_value(subscription, "custom_message", DEFAULT_SETTINGS["youtube"]["custom_message"])),
                "mention_role_id": str(_value(subscription, "mention_role_id", "")),
                "check_interval": int(_value(subscription, "check_interval", 300)),
            })

        autorole = db.get_autorole_settings(guild_id)
        if autorole is not None:
            settings["autorole"].update({
                "enabled": bool(_value(autorole, "enabled", 0)),
                "role_id": str(_value(autorole, "role_id", "")),
            })

        modlogs = db.get_modlog_settings(guild_id)
        if modlogs is not None:
            settings["modlogs"].update({
                "enabled": bool(_value(modlogs, "enabled", 0)),
                "channel_id": str(_value(modlogs, "channel_id", "")),
                "log_members": bool(_value(modlogs, "log_members", 1)),
                "log_messages": bool(_value(modlogs, "log_messages", 1)),
                "log_voice": bool(_value(modlogs, "log_voice", 1)),
                "log_channels": bool(_value(modlogs, "log_channels", 1)),
                "log_bans": bool(_value(modlogs, "log_bans", 1)),
            })

        antispam = db.get_antispam_settings(guild_id)
        if antispam is not None:
            settings["antispam"].update({
                "enabled": bool(_value(antispam, "enabled", 0)),
                "max_messages": int(_value(antispam, "max_messages", 6)),
                "interval_seconds": int(_value(antispam, "interval_seconds", 8)),
                "duplicate_limit": int(_value(antispam, "duplicate_limit", 3)),
                "mention_limit": int(_value(antispam, "mention_limit", 5)),
                "timeout_minutes": int(_value(antispam, "timeout_minutes", 10)),
                "delete_messages": bool(_value(antispam, "delete_messages", 1)),
            })

        tickets = db.get_ticket_settings(guild_id)
        if tickets is not None:
            settings["tickets"].update({
                "enabled": bool(_value(tickets, "enabled", 0)),
                "panel_channel_id": str(_value(tickets, "panel_channel_id", "")),
                "category_id": str(_value(tickets, "category_id", "")),
                "support_role_id": str(_value(tickets, "support_role_id", "")),
                "log_channel_id": str(_value(tickets, "log_channel_id", "")),
            })

        return settings

    async def update_module(self, guild_id: str, module: str, values: dict[str, Any]) -> None:
        handlers = {
            "general": self._save_general_sync,
            "welcome": self._save_welcome_sync,
            "youtube": self._save_youtube_sync,
            "autorole": self._save_autorole_sync,
            "modlogs": self._save_modlogs_sync,
            "antispam": self._save_antispam_sync,
            "tickets": self._save_tickets_sync,
        }
        handler = handlers.get(module)
        if handler is None:
            raise ValueError(f"Neznámý dashboard modul: {module}")
        await asyncio.to_thread(handler, int(guild_id), values)

    def _save_general_sync(self, guild_id: int, values: dict[str, Any]) -> None:
        command_channel_id = _discord_id(
            values.get("command_channel_id"),
            field="ID kanálu pro příkazy",
        )
        db.set_guild_settings(
            guild_id=guild_id,
            language=str(values.get("language") or "cs"),
            timezone_name=str(values.get("timezone") or "Europe/Prague"),
            command_channel_id=command_channel_id,
        )

    def _save_welcome_sync(self, guild_id: int, values: dict[str, Any]) -> None:
        enabled = bool(values.get("enabled"))
        channel_id = _discord_id(
            values.get("channel_id"),
            field="Welcome kanál",
            required=enabled,
        )
        db.update_welcome_settings(
            guild_id=guild_id,
            enabled=enabled,
            channel_id=channel_id,
            message=str(values.get("message") or DEFAULT_SETTINGS["welcome"]["message"]).strip(),
            embed_title=str(values.get("embed_title") or "Vítej!").strip(),
            embed_color=str(values.get("embed_color") or "#5865F2").strip(),
            dm_enabled=bool(values.get("dm_enabled")),
        )

    def _save_autorole_sync(self, guild_id: int, values: dict[str, Any]) -> None:
        enabled = bool(values.get("enabled"))
        role_id = _discord_id(
            values.get("role_id"),
            field="AutoRole",
            required=enabled,
        )
        if role_id is not None:
            db.set_autorole_settings(guild_id, role_id, enabled=enabled)
        else:
            db.set_autorole_enabled(guild_id, False)

    def _save_modlogs_sync(self, guild_id: int, values: dict[str, Any]) -> None:
        enabled = bool(values.get("enabled"))
        channel_id = _discord_id(
            values.get("channel_id"),
            field="ModLog kanál",
            required=enabled,
        )
        if channel_id is not None:
            db.set_modlog_settings(
                guild_id,
                channel_id,
                enabled=enabled,
                log_members=bool(values.get("log_members")),
                log_messages=bool(values.get("log_messages")),
                log_voice=bool(values.get("log_voice")),
                log_channels=bool(values.get("log_channels")),
                log_bans=bool(values.get("log_bans")),
            )
        else:
            db.set_modlog_enabled(guild_id, False)

    def _save_antispam_sync(self, guild_id: int, values: dict[str, Any]) -> None:
        db.set_antispam_settings(
            guild_id,
            enabled=bool(values.get("enabled")),
            max_messages=int(values.get("max_messages") or 6),
            interval_seconds=int(values.get("interval_seconds") or 8),
            duplicate_limit=int(values.get("duplicate_limit") or 3),
            mention_limit=int(values.get("mention_limit") or 5),
            timeout_minutes=int(values.get("timeout_minutes") or 10),
            delete_messages=bool(values.get("delete_messages")),
        )

    def _save_tickets_sync(self, guild_id: int, values: dict[str, Any]) -> None:
        enabled = bool(values.get("enabled"))
        panel_channel_id = _discord_id(
            values.get("panel_channel_id"), field="Kanál ticket panelu",
            required=enabled,
        )
        category_id = _discord_id(
            values.get("category_id"), field="Kategorie ticketů",
            required=enabled,
        )
        support_role_id = _discord_id(
            values.get("support_role_id"), field="Role podpory",
            required=enabled,
        )
        log_channel_id = _discord_id(
            values.get("log_channel_id"), field="Ticket log kanál",
        )
        if panel_channel_id and category_id and support_role_id:
            db.set_ticket_settings(
                guild_id,
                panel_channel_id,
                category_id,
                support_role_id,
                log_channel_id,
                enabled=enabled,
            )
        else:
            db.set_ticket_enabled(guild_id, False)

    def _save_youtube_sync(self, guild_id: int, values: dict[str, Any]) -> None:
        enabled = bool(values.get("enabled"))
        youtube_channel_id = str(values.get("youtube_channel_id") or "").strip()

        if enabled and not youtube_channel_id:
            raise ValueError("YouTube Channel ID je povinné.")

        if not youtube_channel_id:
            # Když není vybraný konkrétní kanál, pozastav všechny odběry serveru.
            for subscription in db.get_guild_subscriptions(guild_id):
                db.pause_subscription(guild_id, str(_value(subscription, "youtube_channel_id", "")))
            return

        discord_channel_id = _discord_id(
            values.get("channel_id"),
            field="Cílový Discord kanál",
            required=enabled,
        )
        mention_role_id = _discord_id(
            values.get("mention_role_id"),
            field="Role pro označení",
        )
        check_interval = max(60, min(int(values.get("check_interval") or 300), 3600))
        custom_message = str(values.get("custom_message") or DEFAULT_SETTINGS["youtube"]["custom_message"]).strip()

        existing_ids = {
            str(_value(row, "youtube_channel_id", ""))
            for row in db.get_guild_subscriptions(guild_id)
        }

        if youtube_channel_id not in existing_ids:
            db.add_youtube_channel(
                youtube_channel_id,
                youtube_channel_id,
                f"https://www.youtube.com/channel/{youtube_channel_id}",
            )
            if discord_channel_id is None:
                raise ValueError("Cílový Discord kanál je povinný pro nový odběr.")
            db.add_subscription(
                guild_id,
                youtube_channel_id,
                discord_channel_id,
                mention_role_id,
            )

        # Při vypnutí ponechá data, pouze odběr pozastaví.
        if discord_channel_id is None:
            rows = list(db.get_guild_subscriptions(guild_id))
            current = next(
                (row for row in rows if str(_value(row, "youtube_channel_id", "")) == youtube_channel_id),
                None,
            )
            if current is None:
                return
            discord_channel_id = int(_value(current, "discord_channel_id", 0))

        db.update_subscription_settings(
            guild_id,
            youtube_channel_id,
            discord_channel_id=discord_channel_id,
            mention_role_id=mention_role_id,
            enabled=enabled,
            custom_message=custom_message,
            check_interval=check_interval,
        )

    async def count_configured_guilds(self, guild_ids: list[str]) -> int:
        return await asyncio.to_thread(
            db.count_configured_guilds,
            [int(guild_id) for guild_id in guild_ids],
        )
