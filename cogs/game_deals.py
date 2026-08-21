"""Oznámení PC her zdarma a výrazných slev."""

from __future__ import annotations

import asyncio
import os

import discord
from discord import app_commands
from discord.ext import commands, tasks

from services.game_deals import (
    ALL_STORE_KEYS,
    STORE_LABELS,
    GameDealsAPIError,
    GameOffer,
    game_deals_api,
)
from utils.db.game_deals import DEFAULT_STORE_FILTERS, MAX_WATCHES_PER_USER, normalize_watch_query
from utils.database import db
from utils.logger import logger
from utils.service_health import mark_error, mark_success


CHECK_MINUTES = max(15, int(os.getenv("GAME_DEALS_CHECK_INTERVAL_MINUTES", "30")))
MAX_SEND_PER_KIND = 5

CATEGORY_LABELS = {
    "free": "🎁 Hra zdarma",
    "weekend": "🗓️ Víkend zdarma",
    "dlc": "🧩 DLC zdarma",
    "deal": "🔥 Herní sleva",
}


def _row_value(row, key: str, default=None):
    try:
        value = row[key]
    except (KeyError, IndexError, TypeError):
        return default
    return default if value is None else value


def parse_store_filters(value: str | None) -> tuple[str, ...]:
    requested = {
        item.strip().lower()
        for item in (value or "").split(",")
        if item.strip()
    }
    return tuple(key for key in ALL_STORE_KEYS if key in requested)


def offer_matches_settings(row, offer: GameOffer) -> bool:
    enabled_key = {
        "free": "enabled_free",
        "weekend": "enabled_weekend",
        "dlc": "enabled_dlc",
        "deal": "enabled_deals",
    }[offer.category]
    if not bool(_row_value(row, enabled_key, 0)):
        return False
    if offer.category == "deal" and (offer.discount or 0) < int(
        _row_value(row, "min_discount", 60)
    ):
        return False
    filters = parse_store_filters(
        str(_row_value(row, "store_filters", DEFAULT_STORE_FILTERS))
    )
    return bool(filters and set(offer.store_keys).intersection(filters))


def offer_matches_watch(query: str, offer: GameOffer) -> bool:
    """Vyhledávání je záměrně jednoduché a předvídatelné: část názvu hry."""
    normalized = normalize_watch_query(query)
    return bool(normalized and normalized in normalize_watch_query(offer.title))


def game_deals_enabled(row) -> bool:
    return row is not None and any(
        bool(_row_value(row, key, 0))
        for key in ("enabled_free", "enabled_weekend", "enabled_dlc", "enabled_deals")
    )


class OfferView(discord.ui.View):
    def __init__(self, url: str) -> None:
        super().__init__(timeout=None)
        self.add_item(discord.ui.Button(label="Otevřít nabídku", emoji="🔗", url=url))


def build_offer_embed(offer: GameOffer) -> discord.Embed:
    free = offer.category != "deal"
    embed = discord.Embed(
        title=f"{CATEGORY_LABELS[offer.category]}: {offer.title}",
        url=offer.url,
        description=offer.description,
        color=discord.Color.green() if free else discord.Color.orange(),
    )
    embed.add_field(name="🏪 Platforma / obchod", value=offer.store, inline=True)
    if offer.sale_price:
        embed.add_field(name="💰 Aktuální cena", value=offer.sale_price, inline=True)
    if offer.normal_price:
        embed.add_field(name="Původní cena", value=offer.normal_price, inline=True)
    if offer.discount and offer.category == "deal":
        embed.add_field(name="📉 Sleva", value=f"{offer.discount} %", inline=True)
    if offer.ends_at and offer.ends_at.lower() not in {"n/a", ""}:
        embed.add_field(name="⏳ Konec nabídky", value=offer.ends_at, inline=False)
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
        need_free = any(
            bool(_row_value(row, key, 0))
            for row in rows
            for key in ("enabled_free", "enabled_weekend", "enabled_dlc")
        )
        need_deals = any(bool(_row_value(row, "enabled_deals", 0)) for row in rows)
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
                watches = await asyncio.to_thread(db.get_game_deal_watches, guild_id)
                batches: list[tuple[str, list[GameOffer]]] = []
                free_offers = [offer for offer in free if offer_matches_settings(row, offer)]
                deal_offers = [offer for offer in deals if offer_matches_settings(row, offer)]
                if any(
                    bool(_row_value(row, key, 0))
                    for key in ("enabled_free", "enabled_weekend", "enabled_dlc")
                ):
                    batches.append(("free", free_offers))
                if bool(_row_value(row, "enabled_deals", 0)):
                    batches.append(("deals", deal_offers))

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
                        await self._notify_watchers(guild_id, watches, offer)
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

    async def _notify_watchers(self, guild_id: int, watches, offer: GameOffer) -> None:
        if not watches:
            return
        guild = self.bot.get_guild(guild_id)
        guild_name = guild.name if guild else "Discord serveru"
        for watch in watches:
            if not offer_matches_watch(str(watch["normalized_query"]), offer):
                continue
            user_id = int(watch["user_id"])
            already_notified = await asyncio.to_thread(
                db.game_deal_watch_was_notified,
                guild_id,
                user_id,
                offer.source,
                offer.offer_id,
            )
            if already_notified:
                continue
            try:
                user = self.bot.get_user(user_id) or await self.bot.fetch_user(user_id)
                embed = build_offer_embed(offer)
                embed.title = f"🔔 Sledovaná hra: {offer.title}"
                await user.send(
                    content=(
                        f"Na serveru **{guild_name}** jsem našel nabídku odpovídající "
                        f"sledování **{watch['query']}**."
                    ),
                    embed=embed,
                    view=OfferView(offer.url),
                )
            except (discord.Forbidden, discord.NotFound):
                logger.info(
                    "Uživateli %s nelze poslat upozornění na sledovanou hru (zavřené DM).",
                    user_id,
                )
            except discord.HTTPException:
                logger.warning(
                    "Soukromé upozornění na hru pro uživatele %s se nepodařilo odeslat.",
                    user_id,
                )
                continue
            await asyncio.to_thread(
                db.mark_game_deal_watch_notified,
                guild_id,
                user_id,
                offer.source,
                offer.offer_id,
            )

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
                view=OfferView(offer.url),
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
        vikendy="Oznamovat víkendy zdarma",
        dlc="Oznamovat DLC zdarma",
        slevy="Oznamovat výrazné slevy",
        minimalni_sleva="Minimální sleva v procentech (10–95)",
        obchody="Obchody oddělené čárkou, například steam,epic,gog",
        role="Volitelná role k označení",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def configure(
        self,
        interaction: discord.Interaction,
        kanal: discord.TextChannel,
        hry_zdarma: bool = True,
        vikendy: bool = True,
        dlc: bool = True,
        slevy: bool = True,
        minimalni_sleva: app_commands.Range[int, 10, 95] = 60,
        obchody: str = DEFAULT_STORE_FILTERS,
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
        stores = ",".join(parse_store_filters(obchody))
        if not stores:
            await interaction.response.send_message(
                "❌ Vyber alespoň jeden obchod: steam, epic, gog, itch, ea, ubisoft, microsoft, humble nebo other.",
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
            vikendy,
            dlc,
            stores,
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
        if row is None or not any(
            bool(_row_value(row, key, 0))
            for key in ("enabled_free", "enabled_weekend", "enabled_dlc", "enabled_deals")
        ):
            await interaction.response.send_message("🎮 Herní nabídky nejsou zapnuté.", ephemeral=True)
            return
        seen = await asyncio.to_thread(db.count_seen_game_deals, interaction.guild.id)
        embed = discord.Embed(title="🎮 Herní nabídky", color=discord.Color.blurple())
        embed.add_field(name="Kanál", value=f"<#{row['channel_id']}>", inline=False)
        embed.add_field(name="Hry zdarma", value="Ano" if row["enabled_free"] else "Ne", inline=True)
        embed.add_field(name="Víkendy zdarma", value="Ano" if _row_value(row, "enabled_weekend", 0) else "Ne", inline=True)
        embed.add_field(name="DLC zdarma", value="Ano" if _row_value(row, "enabled_dlc", 0) else "Ne", inline=True)
        embed.add_field(name="Slevy", value="Ano" if row["enabled_deals"] else "Ne", inline=True)
        embed.add_field(name="Minimální sleva", value=f"{row['min_discount']} %", inline=True)
        embed.add_field(name="Evidovaných nabídek", value=str(seen), inline=True)
        selected_stores = parse_store_filters(str(_row_value(row, "store_filters", DEFAULT_STORE_FILTERS)))
        embed.add_field(
            name="Obchody",
            value=", ".join(STORE_LABELS[key] for key in selected_stores) or "Žádné",
            inline=False,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="seznam", description="Ukáže aktuální hry zdarma, DLC, víkendy a slevy.")
    async def listing(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message("❌ Použij příkaz na serveru.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        row = await asyncio.to_thread(db.get_game_deal_settings, interaction.guild.id)
        if row is None:
            row = {
                "enabled_free": 1,
                "enabled_weekend": 1,
                "enabled_dlc": 1,
                "enabled_deals": 1,
                "min_discount": 60,
                "store_filters": DEFAULT_STORE_FILTERS,
            }
        try:
            free, deals = await self._fetch([row])
        except GameDealsAPIError as exc:
            await interaction.followup.send(f"❌ Aktuální nabídky se nepodařilo načíst: {exc}", ephemeral=True)
            return
        offers = [offer for offer in [*free, *deals] if offer_matches_settings(row, offer)]
        if not offers:
            await interaction.followup.send("🎮 Pro aktuální filtry nejsou žádné nabídky.", ephemeral=True)
            return
        embed = discord.Embed(
            title="🎮 Aktuální herní nabídky",
            description="Výpis respektuje nastavení tohoto serveru.",
            color=discord.Color.blurple(),
        )
        for offer in offers[:10]:
            price = offer.sale_price or "—"
            discount = f" · {offer.discount} %" if offer.category == "deal" and offer.discount else ""
            embed.add_field(
                name=f"{CATEGORY_LABELS[offer.category]} · {offer.title}"[:256],
                value=f"{offer.store} · **{price}{discount}**\n[Přejít na nabídku]({offer.url})",
                inline=False,
            )
        embed.set_footer(text=f"Zobrazeno {min(len(offers), 10)} z {len(offers)} nabídek · GamerPower / CheapShark")
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="sledovat", description="Pošle ti DM, až se objeví sledovaná hra.")
    @app_commands.describe(nazev="Název hry nebo jeho část, například Baldur's Gate")
    async def watch(self, interaction: discord.Interaction, nazev: str) -> None:
        if interaction.guild is None:
            await interaction.response.send_message("❌ Použij příkaz na serveru.", ephemeral=True)
            return
        query = " ".join(nazev.split())
        if not 2 <= len(query) <= 80:
            await interaction.response.send_message(
                "❌ Název musí mít 2 až 80 znaků.", ephemeral=True
            )
            return
        settings = await asyncio.to_thread(db.get_game_deal_settings, interaction.guild.id)
        if not game_deals_enabled(settings):
            await interaction.response.send_message(
                "❌ Na tomto serveru nejsou aktivní herní nabídky. Správce je musí nejdřív nastavit přes `/hry nastavit` nebo dashboard.",
                ephemeral=True,
            )
            return
        try:
            created = await asyncio.to_thread(
                db.add_game_deal_watch, interaction.guild.id, interaction.user.id, query
            )
        except ValueError as exc:
            await interaction.response.send_message(f"❌ {exc}", ephemeral=True)
            return
        if not created:
            await interaction.response.send_message(
                f"ℹ️ **{query}** už sleduješ na tomto serveru.", ephemeral=True
            )
            return
        await interaction.response.send_message(
            f"✅ Sleduješ **{query}**. Pokud bude tvé soukromé zprávy od bota možné doručit, pošlu ti upozornění na novou shodnou nabídku. Limit: {MAX_WATCHES_PER_USER} her.",
            ephemeral=True,
        )

    @app_commands.command(name="sledovane", description="Ukáže tvé sledované hry na tomto serveru.")
    async def watches(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message("❌ Použij příkaz na serveru.", ephemeral=True)
            return
        rows = await asyncio.to_thread(
            db.get_game_deal_watches, interaction.guild.id, interaction.user.id
        )
        if not rows:
            await interaction.response.send_message(
                "🎮 Zatím nesleduješ žádnou hru. Použij `/hry sledovat`.", ephemeral=True
            )
            return
        names = "\n".join(f"• {row['query']}" for row in rows)
        embed = discord.Embed(
            title="🔔 Tvé sledované hry",
            description=names,
            color=discord.Color.blurple(),
        )
        embed.set_footer(text=f"{len(rows)} z {MAX_WATCHES_PER_USER} sledovaných her na tomto serveru")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="nesledovat", description="Odebere hru z tvého sledování.")
    @app_commands.describe(nazev="Přesný název, který vidíš v /hry sledovane")
    async def unwatch(self, interaction: discord.Interaction, nazev: str) -> None:
        if interaction.guild is None:
            await interaction.response.send_message("❌ Použij příkaz na serveru.", ephemeral=True)
            return
        query = " ".join(nazev.split())
        removed = await asyncio.to_thread(
            db.remove_game_deal_watch, interaction.guild.id, interaction.user.id, query
        )
        if not removed:
            await interaction.response.send_message(
                f"ℹ️ **{query}** ve sledování na tomto serveru nemáš.", ephemeral=True
            )
            return
        await interaction.response.send_message(
            f"✅ Přestal(a) jsi sledovat **{query}**.", ephemeral=True
        )

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
            False,
            False,
            str(_row_value(row, "store_filters", DEFAULT_STORE_FILTERS)),
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
