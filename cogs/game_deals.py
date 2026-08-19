"""Oznámení PC her zdarma a výrazných slev."""

from __future__ import annotations

import asyncio
import os

import discord
from discord import app_commands
from discord.ext import commands, tasks

from services.game_deals import GameDealsAPIError, GameOffer, game_deals_api
from utils.database import db
from utils.logger import logger
from utils.service_health import mark_error, mark_success


CHECK_MINUTES = max(15, int(os.getenv("GAME_DEALS_CHECK_INTERVAL_MINUTES", "30")))
MAX_SEND_PER_KIND = 5


def build_offer_embed(offer: GameOffer) -> discord.Embed:
    free = offer.source == "gamerpower"
    embed = discord.Embed(
        title=("🎁 Hra zdarma: " if free else "🔥 Herní sleva: ") + offer.title,
        url=offer.url,
        description=offer.description,
        color=discord.Color.green() if free else discord.Color.orange(),
    )
    embed.add_field(name="🏪 Platforma / obchod", value=offer.store, inline=True)
    if offer.sale_price:
        embed.add_field(name="💰 Aktuální cena", value=offer.sale_price, inline=True)
    if offer.normal_price:
        embed.add_field(name="Původní cena", value=offer.normal_price, inline=True)
    if offer.discount:
        embed.add_field(name="📉 Sleva", value=f"{offer.discount} %", inline=True)
    if offer.ends_at and offer.ends_at.lower() not in {"n/a", ""}:
        embed.add_field(name="⏳ Konec nabídky", value=offer.ends_at, inline=False)
    embed.add_field(name="🔗 Otevřít nabídku", value=f"[Přejít do obchodu]({offer.url})", inline=False)
    if free:
        embed.add_field(
            name="Zdroj",
            value="[GamerPower.com](https://www.gamerpower.com/)",
            inline=False,
        )
    if offer.image_url:
        embed.set_image(url=offer.image_url)
    attribution = "GamerPower.com" if free else "CheapShark.com · ceny v USD"
    embed.set_footer(text=f"Piticko Bot • data: {attribution}")
    return embed


class GameDeals(commands.GroupCog, group_name="hry"):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._lock = asyncio.Lock()
        self.watcher.change_interval(minutes=CHECK_MINUTES)
        self.watcher.start()

    def cog_unload(self) -> None:
        self.watcher.cancel()

    @tasks.loop(minutes=30)
    async def watcher(self) -> None:
        await self.check_all()

    @watcher.before_loop
    async def before_watcher(self) -> None:
        await self.bot.wait_until_ready()

    @watcher.error
    async def watcher_error(self, error: Exception) -> None:
        mark_error("game_deals", error)
        logger.exception("Watcher herních nabídek selhal: %s", error)

    async def _fetch(self, rows) -> tuple[list[GameOffer], list[GameOffer]]:
        need_free = any(bool(row["enabled_free"]) for row in rows)
        need_deals = any(bool(row["enabled_deals"]) for row in rows)
        free: list[GameOffer] = []
        deals: list[GameOffer] = []
        if need_free:
            free = await game_deals_api.fetch_free_games()
        if need_deals:
            deals = await game_deals_api.fetch_discounted_games()
        return free, deals

    async def check_all(self, guild_id: int | None = None) -> tuple[int, int]:
        if self._lock.locked():
            return 0, 0
        async with self._lock:
            rows = await asyncio.to_thread(db.get_enabled_game_deal_settings)
            if guild_id is not None:
                rows = [row for row in rows if int(row["guild_id"]) == guild_id]
            if not rows:
                mark_success("game_deals", "Žádné aktivní odběry.")
                return 0, 0
            try:
                free, deals = await self._fetch(rows)
            except GameDealsAPIError as exc:
                mark_error("game_deals", exc)
                logger.warning("Načtení herních nabídek selhalo: %s", exc)
                return 0, 0

            found = sent = 0
            for row in rows:
                guild_id = int(row["guild_id"])
                batches: list[tuple[str, list[GameOffer]]] = []
                if row["enabled_free"]:
                    batches.append(("free", free))
                if row["enabled_deals"]:
                    minimum = int(row["min_discount"] or 60)
                    batches.append(("deals", [o for o in deals if (o.discount or 0) >= minimum]))

                for kind, offers in batches:
                    initialized = await asyncio.to_thread(
                        db.game_deals_initialized, guild_id, kind
                    )
                    if not initialized:
                        for offer in offers:
                            await asyncio.to_thread(
                                db.mark_game_deal_seen,
                                guild_id,
                                offer.source,
                                offer.offer_id,
                            )
                        await asyncio.to_thread(db.set_game_deals_initialized, guild_id, kind)
                        continue

                    sent_kind = 0
                    for offer in offers:
                        if await asyncio.to_thread(
                            db.game_deal_seen, guild_id, offer.source, offer.offer_id
                        ):
                            continue
                        found += 1
                        if sent_kind >= MAX_SEND_PER_KIND:
                            continue
                        if await self._send(row, offer):
                            await asyncio.to_thread(
                                db.mark_game_deal_seen,
                                guild_id,
                                offer.source,
                                offer.offer_id,
                            )
                            sent += 1
                            sent_kind += 1

            mark_success("game_deals", f"Nových nabídek: {found}, odesláno: {sent}")
            return found, sent

    async def _send(self, row, offer: GameOffer) -> bool:
        channel_id = int(row["channel_id"])
        channel = self.bot.get_channel(channel_id)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(channel_id)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                logger.warning("Kanál herních nabídek %s není dostupný.", channel_id)
                return False
        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            return False
        role_id = row["mention_role_id"]
        try:
            await channel.send(
                content=f"<@&{role_id}>" if role_id else None,
                embed=build_offer_embed(offer),
                allowed_mentions=discord.AllowedMentions(roles=True, users=False, everyone=False),
            )
            return True
        except discord.HTTPException:
            logger.exception("Odeslání herní nabídky do %s selhalo.", channel_id)
            return False

    @app_commands.command(name="nastavit", description="Nastaví oznámení her zdarma a slev.")
    @app_commands.describe(
        kanal="Kanál pro oznámení",
        hry_zdarma="Oznamovat časově omezené hry zdarma",
        slevy="Oznamovat výrazné slevy",
        minimalni_sleva="Minimální sleva v procentech (10–95)",
        role="Volitelná role k označení",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def configure(
        self,
        interaction: discord.Interaction,
        kanal: discord.TextChannel,
        hry_zdarma: bool = True,
        slevy: bool = True,
        minimalni_sleva: app_commands.Range[int, 10, 95] = 60,
        role: discord.Role | None = None,
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message("❌ Použij příkaz na serveru.", ephemeral=True)
            return
        me = interaction.guild.me
        permissions = kanal.permissions_for(me) if me else None
        if not permissions or not permissions.view_channel or not permissions.send_messages:
            await interaction.response.send_message(
                "❌ Bot v kanálu potřebuje oprávnění Zobrazit kanál a Posílat zprávy.",
                ephemeral=True,
            )
            return
        await asyncio.to_thread(
            db.set_game_deal_settings,
            interaction.guild.id,
            kanal.id,
            role.id if role else None,
            hry_zdarma,
            slevy,
            int(minimalni_sleva),
        )
        await interaction.response.send_message(
            f"✅ Herní nabídky budou chodit do {kanal.mention}. První kontrola pouze "
            "uloží současné nabídky, aby kanál nebyl zaplaven.",
            ephemeral=True,
        )

    @app_commands.command(name="stav", description="Ukáže nastavení herních nabídek.")
    async def status(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message("❌ Použij příkaz na serveru.", ephemeral=True)
            return
        row = await asyncio.to_thread(db.get_game_deal_settings, interaction.guild.id)
        if row is None or not (row["enabled_free"] or row["enabled_deals"]):
            await interaction.response.send_message("🎮 Herní nabídky nejsou zapnuté.", ephemeral=True)
            return
        seen = await asyncio.to_thread(db.count_seen_game_deals, interaction.guild.id)
        embed = discord.Embed(title="🎮 Herní nabídky", color=discord.Color.blurple())
        embed.add_field(name="Kanál", value=f"<#{row['channel_id']}>", inline=False)
        embed.add_field(name="Hry zdarma", value="Ano" if row["enabled_free"] else "Ne", inline=True)
        embed.add_field(name="Slevy", value="Ano" if row["enabled_deals"] else "Ne", inline=True)
        embed.add_field(name="Minimální sleva", value=f"{row['min_discount']} %", inline=True)
        embed.add_field(name="Evidovaných nabídek", value=str(seen), inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="kontrola", description="Ručně zkontroluje nové herní nabídky.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def check(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message("❌ Použij příkaz na serveru.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        found, sent = await self.check_all(interaction.guild.id)
        await interaction.followup.send(
            f"✅ Kontrola dokončena. Nových: **{found}**, odesláno: **{sent}**.",
            ephemeral=True,
        )

    @app_commands.command(name="vypnout", description="Vypne herní nabídky.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def disable(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message("❌ Použij příkaz na serveru.", ephemeral=True)
            return
        row = await asyncio.to_thread(db.get_game_deal_settings, interaction.guild.id)
        await asyncio.to_thread(
            db.set_game_deal_settings,
            interaction.guild.id,
            int(row["channel_id"]) if row and row["channel_id"] else None,
            int(row["mention_role_id"]) if row and row["mention_role_id"] else None,
            False,
            False,
            int(row["min_discount"] if row else 60),
        )
        await interaction.response.send_message("✅ Herní nabídky byly vypnuté.", ephemeral=True)

    async def cog_app_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        original = getattr(error, "original", error)
        message = (
            "❌ Potřebuješ oprávnění **Spravovat server**."
            if isinstance(original, app_commands.MissingPermissions)
            else "❌ Příkaz herních nabídek selhal."
        )
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(GameDeals(bot))
