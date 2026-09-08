"""Automatické odesílání oznámení naplánovaných v dashboardu."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import discord
from discord.ext import commands, tasks

from config import EMBED_COLOR, EMBED_FOOTER
from utils.database import db


log = logging.getLogger(__name__)


def parse_color(value: str) -> discord.Color:
    """Vrátí platnou barvu embedu, i když je hodnota v DB poškozená."""
    try:
        return discord.Color(int(str(value).lstrip("#"), 16))
    except (TypeError, ValueError):
        return discord.Color(EMBED_COLOR)


def row_value(row, key: str, default=None):
    try:
        value = row[key]
    except (KeyError, IndexError, TypeError):
        return default
    return default if value is None else value


def next_scheduled_time(announcement, now: datetime) -> str | None:
    """Spočítá další lokální termín; neuteče kvůli přechodu na letní čas."""
    repeat_kind = str(row_value(announcement, "repeat_kind", "once"))
    if repeat_kind not in {"daily", "weekly"}:
        return None
    try:
        scheduled = datetime.fromisoformat(str(announcement["scheduled_at"]))
        if scheduled.tzinfo is None:
            scheduled = scheduled.replace(tzinfo=timezone.utc)
        timezone_name = str(row_value(announcement, "timezone_name", "Europe/Prague"))
        local = scheduled.astimezone(ZoneInfo(timezone_name))
    except (TypeError, ValueError, ZoneInfoNotFoundError):
        return None

    step = timedelta(days=1 if repeat_kind == "daily" else 7)
    next_local = local + step
    while next_local.astimezone(timezone.utc) <= now:
        next_local += step
    return next_local.astimezone(timezone.utc).isoformat()


class ScheduledAnnouncements(commands.Cog):
    """Každých 30 sekund odešle oznámení, jejichž čas právě nastal."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._lock = asyncio.Lock()
        self.sender.start()

    def cog_unload(self) -> None:
        self.sender.cancel()

    @staticmethod
    def build_embed(announcement) -> discord.Embed:
        title = str(announcement["title"] or "📣 Oznámení")[:256]
        embed = discord.Embed(
            title=title,
            description=str(announcement["content"])[:4000],
            color=parse_color(str(announcement["color"] or "")),
        )
        embed.set_footer(text=EMBED_FOOTER)
        return embed

    async def resolve_channel(self, announcement) -> discord.abc.Messageable | None:
        guild = self.bot.get_guild(int(announcement["guild_id"]))
        if guild is None:
            return None
        channel_id = int(announcement["channel_id"])
        channel = guild.get_channel(channel_id)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(channel_id)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                return None
        if isinstance(channel, (discord.TextChannel, discord.Thread)):
            return channel
        return None

    @tasks.loop(seconds=30)
    async def sender(self) -> None:
        async with self._lock:
            now = datetime.now(timezone.utc).isoformat()
            due = await asyncio.to_thread(db.get_due_scheduled_announcements, now)
            for announcement in due:
                announcement_id = int(announcement["id"])
                channel = await self.resolve_channel(announcement)
                if channel is None:
                    # Neexistující nebo botovi nedostupný kanál se sám nezlepší.
                    await asyncio.to_thread(db.mark_scheduled_announcement_failed, announcement_id)
                    log.warning("Plánované oznámení %s nelze odeslat: kanál není dostupný.", announcement_id)
                    continue
                try:
                    message = await channel.send(
                        embed=self.build_embed(announcement),
                        # Plánovaná zpráva nemůže omylem pingnout @everyone ani role.
                        allowed_mentions=discord.AllowedMentions.none(),
                    )
                except (discord.Forbidden, discord.NotFound):
                    await asyncio.to_thread(db.mark_scheduled_announcement_failed, announcement_id)
                    log.warning("Plánované oznámení %s Discord odmítl.", announcement_id)
                except discord.HTTPException:
                    # Krátký výpadek Discordu neznamená ztrátu zprávy; zkusí se znovu.
                    log.exception("Dočasná chyba při odesílání plánovaného oznámení %s.", announcement_id)
                else:
                    next_time = next_scheduled_time(announcement, datetime.now(timezone.utc))
                    if next_time is None:
                        await asyncio.to_thread(
                            db.mark_scheduled_announcement_sent, announcement_id, message.id
                        )
                        log.info("Odesláno jednorázové oznámení %s.", announcement_id)
                    else:
                        await asyncio.to_thread(
                            db.reschedule_scheduled_announcement,
                            announcement_id, message.id, next_time,
                        )
                        log.info("Odesláno opakované oznámení %s; další termín %s.", announcement_id, next_time)

    @sender.before_loop
    async def before_sender(self) -> None:
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ScheduledAnnouncements(bot))
