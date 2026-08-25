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
        "youtube_channel_name": "",
        "custom_message": "📺 Nové video: {title}\n{url}",
        "mention_role_id": "",
        "subscription_role_free_id": "",
        "subscription_role_weekend_id": "",
        "subscription_role_dlc_id": "",
        "subscription_role_deal_id": "",
        "check_interval": 300,
        "live_enabled": False,
        "live_notify_upcoming": False,
        "live_custom_message": "🔴 {channel} právě vysílá: {title}\n{url}",
    },
    "autorole": {
        "enabled": False,
        "role_id": "",
    },
    "reaction_roles": {
        "enabled": False,
        "channel_id": "",
        "message_id": "",
        "title": "Vyber si role",
        "description": "Klikni na reakci pod touto zprávou a roli ti přidám. Odebráním reakce se role zase odebere.",
        "entries": [],
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
        "ignored_channel_ids": [],
    },
    "tickets": {
        "enabled": False,
        "panel_channel_id": "",
        "category_id": "",
        "support_role_id": "",
        "log_channel_id": "",
    },
    "pc_advice": {
        "enabled": False,
        "mode": "private",
        "panel_channel_id": "",
        "category_id": "",
        "forum_channel_id": "",
        "advisor_role_id": "",
        "log_channel_id": "",
        "reminders_enabled": False,
        "reminder_days": 3,
    },
    "abi_rank": {
        "enabled": False,
        "review_channel_id": "",
        "reviewer_role_id": "",
        "rookie_role_id": "",
        "vanguard_role_id": "",
        "elite_role_id": "",
        "expert_role_id": "",
        "master_role_id": "",
        "ace_role_id": "",
        "hero_role_id": "",
        "legend_role_id": "",
    },
    "sheep_game": {
        "enabled": False,
        "channel_id": "",
    },
    "game_deals": {
        "enabled_free": False,
        "enabled_weekend": False,
        "enabled_dlc": False,
        "enabled_deals": False,
        "channel_id": "",
        "mention_role_id": "",
        "min_discount": 60,
        "store_filters": ["steam", "epic", "gog", "itch", "ea", "ubisoft", "microsoft", "humble", "other"],
        "seen_count": 0,
    },
    "moderation": {"auto_punishments": False},
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
                "youtube_channel_name": str(_value(subscription, "youtube_name", "")),
                "custom_message": str(_value(subscription, "custom_message", DEFAULT_SETTINGS["youtube"]["custom_message"])),
                "mention_role_id": str(_value(subscription, "mention_role_id", "")),
                "check_interval": int(_value(subscription, "check_interval", 300)),
                "live_enabled": bool(_value(subscription, "live_enabled", 0)),
                "live_notify_upcoming": bool(_value(subscription, "live_notify_upcoming", 0)),
                "live_custom_message": str(_value(subscription, "live_custom_message", DEFAULT_SETTINGS["youtube"]["live_custom_message"])),
            })

        autorole = db.get_autorole_settings(guild_id)
        if autorole is not None:
            settings["autorole"].update({
                "enabled": bool(_value(autorole, "enabled", 0)),
                "role_id": str(_value(autorole, "role_id", "")),
            })

        reaction_roles = db.get_reaction_role_settings(guild_id)
        settings["reaction_roles"].update({
            "enabled": bool(reaction_roles["enabled"]),
            "channel_id": str(reaction_roles["channel_id"]),
            "message_id": str(reaction_roles["message_id"]),
            "title": str(reaction_roles["title"]),
            "description": str(reaction_roles["description"]),
            "entries": list(reaction_roles["entries"]),
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
                "ignored_channel_ids": [
                    value
                    for value in str(
                        _value(antispam, "ignored_channel_ids", "")
                    ).split(",")
                    if value.isdigit()
                ],
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

        pc_advice = db.get_pc_advice_settings(guild_id)
        if pc_advice is not None:
            settings["pc_advice"].update({
                "enabled": bool(_value(pc_advice, "enabled", 0)),
                "mode": str(_value(pc_advice, "mode", "private")),
                "panel_channel_id": str(_value(pc_advice, "panel_channel_id", "")),
                "category_id": str(_value(pc_advice, "category_id", "")),
                "forum_channel_id": str(_value(pc_advice, "forum_channel_id", "")),
                "advisor_role_id": str(_value(pc_advice, "advisor_role_id", "")),
                "log_channel_id": str(_value(pc_advice, "log_channel_id", "")),
                "reminders_enabled": bool(
                    _value(pc_advice, "reminders_enabled", 0)
                ),
                "reminder_days": int(_value(pc_advice, "reminder_days", 3)),
            })

        abi_rank = db.get_abi_rank_settings(guild_id)
        if abi_rank is not None:
            settings["abi_rank"].update({
                key: (
                    bool(_value(abi_rank, key, 0))
                    if key == "enabled"
                    else str(_value(abi_rank, key, ""))
                )
                for key in settings["abi_rank"]
            })

        sheep_game = db.get_sheep_game_settings(guild_id)
        if sheep_game is not None:
            settings["sheep_game"].update({
                "enabled": bool(_value(sheep_game, "enabled", 0)),
                "channel_id": str(_value(sheep_game, "channel_id", "")),
            })

        game_deals = db.get_game_deal_settings(guild_id)
        if game_deals is not None:
            settings["game_deals"].update({
                "enabled_free": bool(_value(game_deals, "enabled_free", 0)),
                "enabled_weekend": bool(_value(game_deals, "enabled_weekend", 0)),
                "enabled_dlc": bool(_value(game_deals, "enabled_dlc", 0)),
                "enabled_deals": bool(_value(game_deals, "enabled_deals", 0)),
                "channel_id": str(_value(game_deals, "channel_id", "")),
                "mention_role_id": str(_value(game_deals, "mention_role_id", "")),
                "subscription_role_free_id": str(_value(game_deals, "subscription_role_free_id", "")),
                "subscription_role_weekend_id": str(_value(game_deals, "subscription_role_weekend_id", "")),
                "subscription_role_dlc_id": str(_value(game_deals, "subscription_role_dlc_id", "")),
                "subscription_role_deal_id": str(_value(game_deals, "subscription_role_deal_id", "")),
                "min_discount": int(_value(game_deals, "min_discount", 60)),
                "store_filters": [
                    item for item in str(_value(
                        game_deals,
                        "store_filters",
                        "steam,epic,gog,itch,ea,ubisoft,microsoft,humble,other",
                    )).split(",") if item
                ],
                "seen_count": db.count_seen_game_deals(guild_id),
            })

        with db.connect() as conn:
            moderation = conn.execute(
                "SELECT auto_punishments FROM moderation_settings WHERE guild_id = ?",
                (guild_id,),
            ).fetchone()
        if moderation is not None:
            settings["moderation"]["auto_punishments"] = bool(
                _value(moderation, "auto_punishments", 0)
            )

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
            "pc_advice": self._save_pc_advice_sync,
            "abi_rank": self._save_abi_rank_sync,
            "sheep_game": self._save_sheep_game_sync,
            "game_deals": self._save_game_deals_sync,
            "moderation": self._save_moderation_sync,
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
        ignored_channel_ids = []
        for raw_id in values.get("ignored_channel_ids") or []:
            channel_id = str(raw_id).strip()
            if channel_id.isdigit() and channel_id not in ignored_channel_ids:
                ignored_channel_ids.append(channel_id)

        db.set_antispam_settings(
            guild_id,
            enabled=bool(values.get("enabled")),
            max_messages=int(values.get("max_messages") or 6),
            interval_seconds=int(values.get("interval_seconds") or 8),
            duplicate_limit=int(values.get("duplicate_limit") or 3),
            mention_limit=int(values.get("mention_limit") or 5),
            timeout_minutes=int(values.get("timeout_minutes") or 10),
            delete_messages=bool(values.get("delete_messages")),
            ignored_channel_ids=",".join(ignored_channel_ids[:25]),
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

    def _save_pc_advice_sync(self, guild_id: int, values: dict[str, Any]) -> None:
        enabled = bool(values.get("enabled"))
        mode = str(values.get("mode") or "private")
        if mode not in {"private", "forum", "choice"}:
            raise ValueError("Neplatný režim PC poradny.")
        panel_channel_id = _discord_id(
            values.get("panel_channel_id"), field="Kanál panelu PC poradny",
            required=enabled,
        )
        category_id = _discord_id(
            values.get("category_id"), field="Kategorie PC poradny",
            required=enabled and mode in {"private", "choice"},
        )
        forum_channel_id = _discord_id(
            values.get("forum_channel_id"), field="Fórum PC poradny",
            required=enabled and mode in {"forum", "choice"},
        )
        advisor_role_id = _discord_id(
            values.get("advisor_role_id"), field="Role PC poradců",
            required=enabled,
        )
        log_channel_id = _discord_id(
            values.get("log_channel_id"), field="Log PC poradny",
        )
        reminders_enabled = bool(values.get("reminders_enabled"))
        reminder_days = int(values.get("reminder_days") or 3)
        if not 1 <= reminder_days <= 30:
            raise ValueError("Připomínka PC poradny musí být mezi 1 a 30 dny.")
        effective_category_id = category_id or forum_channel_id
        if panel_channel_id and effective_category_id and advisor_role_id:
            db.set_pc_advice_settings(
                guild_id, panel_channel_id, effective_category_id, advisor_role_id,
                log_channel_id, mode=mode, forum_channel_id=forum_channel_id,
                enabled=enabled, reminders_enabled=reminders_enabled,
                reminder_days=reminder_days,
            )
        else:
            db.set_pc_advice_enabled(guild_id, False)

    def _save_abi_rank_sync(self, guild_id: int, values: dict[str, Any]) -> None:
        enabled = bool(values.get("enabled"))
        review_channel_id = _discord_id(
            values.get("review_channel_id"), field="ABI kontrolní kanál",
            required=enabled,
        )
        reviewer_role_id = _discord_id(
            values.get("reviewer_role_id"), field="Role ABI ověřovatelů",
            required=enabled,
        )
        rank_roles = {
            rank: _discord_id(
                values.get(f"{rank}_role_id"), field=f"ABI role {rank}"
            )
            for rank in (
                "rookie", "vanguard", "elite", "expert",
                "master", "ace", "hero", "legend",
            )
        }
        if review_channel_id and reviewer_role_id:
            db.set_abi_rank_settings(
                guild_id, review_channel_id, reviewer_role_id,
                rank_roles, enabled=enabled,
            )
        else:
            db.set_abi_rank_enabled(guild_id, False)

    def _save_moderation_sync(self, guild_id: int, values: dict[str, Any]) -> None:
        enabled = int(bool(values.get("auto_punishments")))
        with db.connect() as conn:
            excluded = "EXCLUDED" if db.using_postgres else "excluded"
            conn.execute(f"""
                INSERT INTO moderation_settings
                (guild_id, auto_punishments, updated_at) VALUES (?, ?, ?)
                ON CONFLICT (guild_id) DO UPDATE SET
                    auto_punishments = {excluded}.auto_punishments,
                    updated_at = {excluded}.updated_at
            """, (guild_id, enabled, db.now()))
            conn.commit()

    def _save_sheep_game_sync(self, guild_id: int, values: dict[str, Any]) -> None:
        enabled = bool(values.get("enabled"))
        channel_id = _discord_id(
            values.get("channel_id"), field="Kanál počítání oveček", required=enabled
        )
        previous = db.get_sheep_game_settings(guild_id)
        db.set_sheep_game_settings(guild_id, channel_id, enabled)
        if (
            previous is not None
            and _value(previous, "channel_id") != channel_id
        ):
            db.reset_sheep_chain(guild_id)

    def _save_game_deals_sync(self, guild_id: int, values: dict[str, Any]) -> None:
        enabled_free = bool(values.get("enabled_free"))
        enabled_weekend = bool(values.get("enabled_weekend"))
        enabled_dlc = bool(values.get("enabled_dlc"))
        enabled_deals = bool(values.get("enabled_deals"))
        enabled = enabled_free or enabled_weekend or enabled_dlc or enabled_deals
        channel_id = _discord_id(
            values.get("channel_id"), field="Kanál herních nabídek", required=enabled
        )
        mention_role_id = _discord_id(
            values.get("mention_role_id"), field="Role herních nabídek"
        )
        try:
            min_discount = int(values.get("min_discount") or 60)
        except (TypeError, ValueError) as exc:
            raise ValueError("Minimální sleva musí být číslo.") from exc
        if not 10 <= min_discount <= 95:
            raise ValueError("Minimální sleva musí být mezi 10 a 95 %.")
        valid_stores = {"steam", "epic", "gog", "itch", "ea", "ubisoft", "microsoft", "humble", "other"}
        stores = [str(item).lower() for item in values.get("store_filters", [])]
        stores = [item for item in stores if item in valid_stores]
        if enabled and not stores:
            raise ValueError("Vyber alespoň jeden obchod pro herní nabídky.")
        db.set_game_deal_settings(
            guild_id, channel_id, mention_role_id,
            enabled_free, enabled_deals, min_discount,
            enabled_weekend, enabled_dlc, ",".join(dict.fromkeys(stores)),
        )
        for category in ("free", "weekend", "dlc", "deal"):
            role_id = _discord_id(
                values.get(f"subscription_role_{category}_id"),
                field="Role dobrovolného herního odběru",
            )
            db.set_game_deal_subscription_role(guild_id, category, role_id)

    async def get_sheep_game(self, guild_id: str) -> dict[str, Any]:
        return await asyncio.to_thread(self._get_sheep_game_sync, int(guild_id))

    def _get_sheep_game_sync(self, guild_id: int) -> dict[str, Any]:
        settings = db.get_sheep_game_settings(guild_id)
        leaderboard = db.get_sheep_leaderboard(guild_id, 10)
        return {
            "current_count": int(_value(settings, "current_count", 0)),
            "record_count": int(_value(settings, "record_count", 0)),
            "total_valid_counts": int(_value(settings, "total_valid_counts", 0)),
            "leaderboard": [
                {key: row[key] for key in row.keys()} for row in leaderboard
            ],
        }

    def _save_youtube_sync(self, guild_id: int, values: dict[str, Any]) -> None:
        enabled = bool(values.get("enabled"))
        youtube_channel_id = str(values.get("youtube_channel_id") or "").strip()
        youtube_channel_name = str(values.get("youtube_channel_name") or "").strip()

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
        live_custom_message = str(values.get("live_custom_message") or DEFAULT_SETTINGS["youtube"]["live_custom_message"]).strip()

        existing_ids = {
            str(_value(row, "youtube_channel_id", ""))
            for row in db.get_guild_subscriptions(guild_id)
        }

        db.add_youtube_channel(
            youtube_channel_id,
            youtube_channel_name or youtube_channel_id,
            f"https://www.youtube.com/channel/{youtube_channel_id}",
        )

        if youtube_channel_id not in existing_ids:
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
            live_enabled=bool(values.get("live_enabled")),
            live_notify_upcoming=bool(values.get("live_notify_upcoming")),
            live_custom_message=live_custom_message,
        )

    async def count_configured_guilds(self, guild_ids: list[str]) -> int:
        return await asyncio.to_thread(
            db.count_configured_guilds,
            [int(guild_id) for guild_id in guild_ids],
        )

    async def get_giveaways(self, guild_id: str) -> list[dict[str, Any]]:
        return await asyncio.to_thread(self._get_giveaways_sync, int(guild_id))

    def _get_giveaways_sync(self, guild_id: int) -> list[dict[str, Any]]:
        with db.connect() as conn:
            rows = conn.execute("""
                SELECT g.*,
                       (SELECT COUNT(*) FROM giveaway_entries e
                        WHERE e.giveaway_id = g.id) AS entry_count
                FROM giveaways g
                WHERE g.guild_id = ?
                ORDER BY CASE WHEN g.status = 'active' THEN 0 ELSE 1 END,
                         g.id DESC
                LIMIT 25
            """, (guild_id,)).fetchall()
        return [{key: row[key] for key in row.keys()} for row in rows]

    async def get_makejpc_products(self) -> list[dict[str, Any]]:
        return await asyncio.to_thread(self._get_makejpc_products_sync)

    def _get_makejpc_products_sync(self) -> list[dict[str, Any]]:
        rows = list(db.get_makejpc_products())[:50]
        return [{key: row[key] for key in row.keys()} for row in rows]

    async def get_moderation_events(self, guild_id: str) -> list[dict[str, Any]]:
        return await asyncio.to_thread(self._get_moderation_events_sync, int(guild_id))

    def _get_moderation_events_sync(self, guild_id: int) -> list[dict[str, Any]]:
        with db.connect() as conn:
            rows = conn.execute("""
                SELECT id, user_id, moderator_id, 'warn' AS action, reason,
                       NULL AS duration_minutes, created_at
                FROM moderation_warnings WHERE guild_id = ?
                UNION ALL
                SELECT id, user_id, moderator_id, action, reason,
                       duration_minutes, created_at
                FROM moderation_actions WHERE guild_id = ?
                ORDER BY created_at DESC LIMIT 50
            """, (guild_id, guild_id)).fetchall()
        return [{key: row[key] for key in row.keys()} for row in rows]
