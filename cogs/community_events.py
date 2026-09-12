"""Kalendář akcí s přihlašováním přes Discord tlačítko."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

import discord
from discord.ext import commands, tasks

from config import EMBED_COLOR, EMBED_FOOTER
from utils.database import db


log = logging.getLogger(__name__)


def parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


class EventJoinView(discord.ui.View):
    def __init__(self, cog: "CommunityEvents", event_id: int) -> None:
        super().__init__(timeout=None)
        self.cog = cog
        self.event_id = event_id
        button = discord.ui.Button(
            label="Zúčastním se", emoji="✅", style=discord.ButtonStyle.success,
            custom_id=f"piticko:event:join:{event_id}",
        )
        button.callback = self.join
        self.add_item(button)

    async def join(self, interaction: discord.Interaction) -> None:
        event = await asyncio.to_thread(db.get_community_event, self.event_id)
        if event is None or str(event["status"]) != "active":
            await interaction.response.send_message("❌ Tato akce už není aktivní.", ephemeral=True)
            return
        if interaction.guild is None or interaction.guild.id != int(event["guild_id"]):
            await interaction.response.send_message("❌ Tato akce patří na jiný server.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        joined = await asyncio.to_thread(db.join_community_event, self.event_id, interaction.user.id)
        await self.cog.refresh_message(event)
        await interaction.followup.send(
            "✅ Jsi přihlášený na akci." if joined else "ℹ️ Na tuto akci už jsi přihlášený.",
            ephemeral=True,
        )


class CommunityEvents(commands.Cog):
    """Zveřejní akce vytvořené v dashboardu a spravuje jejich účastníky."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.publisher.start()

    def cog_unload(self) -> None:
        self.publisher.cancel()

    async def cog_load(self) -> None:
        for event in await asyncio.to_thread(db.get_active_community_events):
            self.bot.add_view(EventJoinView(self, int(event["id"])), message_id=int(event["message_id"]))

    @staticmethod
    async def build_embed(event) -> discord.Embed:
        participants = await asyncio.to_thread(db.count_community_event_participants, int(event["id"]))
        embed = discord.Embed(
            title=f"📅 {str(event['title'])[:200]}",
            description=str(event["description"])[:2000] or "Bez doplňujícího popisu.",
            color=EMBED_COLOR,
        )
        try:
            event_time = parse_time(str(event["event_at"]))
            time_value = discord.utils.format_dt(event_time, style="F") + "\n" + discord.utils.format_dt(event_time, style="R")
        except ValueError:
            time_value = str(event["event_at"])
        embed.add_field(name="🕒 Kdy", value=time_value, inline=True)
        embed.add_field(name="👥 Přihlášeno", value=str(participants), inline=True)
        embed.set_footer(text=EMBED_FOOTER)
        return embed

    async def get_channel(self, event) -> discord.TextChannel | None:
        guild = self.bot.get_guild(int(event["guild_id"]))
        if guild is None:
            return None
        channel = guild.get_channel(int(event["channel_id"]))
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(int(event["channel_id"]))
            except discord.HTTPException:
                return None
        return channel if isinstance(channel, discord.TextChannel) else None

    async def refresh_message(self, event) -> None:
        if not event["message_id"]:
            return
        channel = await self.get_channel(event)
        if channel is None:
            return
        try:
            message = await channel.fetch_message(int(event["message_id"]))
            await message.edit(embed=await self.build_embed(event), view=EventJoinView(self, int(event["id"])))
        except (discord.NotFound, discord.Forbidden):
            return
        except discord.HTTPException:
            log.exception("Nepodařilo se aktualizovat akci %s.", event["id"])

    @tasks.loop(seconds=20)
    async def publisher(self) -> None:
        for event in await asyncio.to_thread(db.get_pending_community_events):
            channel = await self.get_channel(event)
            if channel is None:
                log.warning("Akci %s nelze zveřejnit: kanál není dostupný.", event["id"])
                continue
            try:
                view = EventJoinView(self, int(event["id"]))
                message = await channel.send(embed=await self.build_embed(event), view=view)
            except discord.HTTPException:
                log.exception("Zveřejnění akce %s selhalo.", event["id"])
                continue
            await asyncio.to_thread(db.publish_community_event, int(event["id"]), message.id)
            self.bot.add_view(view, message_id=message.id)
            log.info("Zveřejněna komunitní akce %s.", event["id"])

    @publisher.before_loop
    async def before_publisher(self) -> None:
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(CommunityEvents(bot))
