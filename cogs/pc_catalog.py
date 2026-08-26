"""Sledování hotových PC sestav ve fórech jednotlivých Discord serverů."""

from __future__ import annotations

import asyncio
import logging

import discord
from discord import app_commands
from discord.ext import commands, tasks

from services.products.base import Product
from services.products.makejpc import MakeJPCProvider
from services.products.sestavsipocitac import SestavSiPocitacProvider
from utils.database import db


log = logging.getLogger(__name__)

SOURCES = {
    "makejpc": ("Makej PC", MakeJPCProvider()),
    "sestavsipocitac": ("SestavSiPočítač", SestavSiPocitacProvider()),
}


def row_value(row, key: str, default=None):
    try:
        value = row[key]
    except (KeyError, IndexError, TypeError):
        return default
    return default if value is None else value


class BuildRefreshView(discord.ui.View):
    def __init__(self, cog: "PcCatalog", guild_id: int, source: str, build_code: str) -> None:
        super().__init__(timeout=None)
        button = discord.ui.Button(
            label="Obnovit sestavu", emoji="🔄", style=discord.ButtonStyle.secondary,
            # ID komponenty Discordu smí mít nejvýše 100 znaků. Guild ID není
            # potřeba: persistentní view se registruje ke konkrétní zprávě.
            custom_id=f"piticko:pc-catalog:r:{source}:{build_code}",
        )

        async def callback(interaction: discord.Interaction) -> None:
            await cog.refresh_from_button(interaction, source, build_code)

        button.callback = callback
        self.add_item(button)


class PcCatalog(commands.GroupCog, group_name="sestavy"):
    """Automaticky zveřejňuje a obnovuje PC sestavy ve fóru."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._lock = asyncio.Lock()
        self.watcher.start()
        self.refresh_requests.start()

    async def cog_load(self) -> None:
        # Načte obnovovací tlačítka i pro příspěvky vytvořené před restartem.
        for post in await asyncio.to_thread(db.get_pc_catalog_posts):
            try:
                self.bot.add_view(
                    BuildRefreshView(
                        self, int(post["guild_id"]), str(post["source"]), str(post["build_code"])
                    ),
                    message_id=int(post["message_id"]),
                )
            except ValueError:
                log.warning("Nelze načíst tlačítko pro sledovanou sestavu %s.", post)

    def cog_unload(self) -> None:
        self.watcher.cancel()
        self.refresh_requests.cancel()

    @staticmethod
    def build_embed(source: str, product: Product) -> discord.Embed:
        source_name = SOURCES[source][0]
        embed = discord.Embed(
            title=product.name,
            url=product.url,
            description=f"Hotová PC sestava z nabídky **{source_name}**.",
            color=discord.Color.blurple(),
        )
        embed.add_field(name="💰 Cena", value=product.price, inline=True)
        embed.add_field(name="📦 Dostupnost", value=product.availability, inline=True)
        embed.add_field(name="🔗 Detail", value=f"[Otevřít sestavu]({product.url})", inline=False)
        if product.image_url:
            embed.set_image(url=product.image_url)
        embed.set_footer(text=f"{source_name} • automaticky spravováno Piticko Botem")
        return embed

    @staticmethod
    def source_is_enabled(settings, source: str) -> bool:
        return bool(row_value(settings, f"enabled_{source}", 0))

    async def fetch_source(self, source: str) -> list[Product]:
        return await SOURCES[source][1].fetch_products()

    async def get_forum(self, forum_id: int) -> discord.ForumChannel | None:
        channel = self.bot.get_channel(forum_id)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(forum_id)
            except discord.HTTPException:
                return None
        return channel if isinstance(channel, discord.ForumChannel) else None

    async def publish_or_update(
        self, guild_id: int, forum: discord.ForumChannel, source: str, product: Product,
        mention_role_id: int | None,
    ) -> str:
        post = await asyncio.to_thread(db.get_pc_catalog_post, guild_id, source, product.code)
        view = BuildRefreshView(self, guild_id, source, product.code)
        if post is not None:
            try:
                channel = self.bot.get_channel(int(post["thread_id"]))
                if channel is None:
                    channel = await self.bot.fetch_channel(int(post["thread_id"]))
                if not isinstance(channel, discord.Thread):
                    raise LookupError("Vlákno není dostupné")
                message = await channel.fetch_message(int(post["message_id"]))
                await message.edit(embed=self.build_embed(source, product), view=view)
                if channel.name != product.thread_name:
                    await channel.edit(name=product.thread_name[:100])
                return "updated"
            except (LookupError, discord.NotFound, discord.Forbidden, discord.HTTPException):
                log.info("Původní fórum příspěvek pro %s/%s nelze obnovit; vytvořím nový.", source, product.code)

        content = f"<@&{mention_role_id}>" if mention_role_id else None
        created = await forum.create_thread(
            name=product.thread_name,
            content=content,
            embed=self.build_embed(source, product),
            view=view,
            allowed_mentions=discord.AllowedMentions(roles=bool(mention_role_id)),
        )
        self.bot.add_view(view, message_id=created.message.id)
        await asyncio.to_thread(
            db.save_pc_catalog_post, guild_id, source, product.code,
            forum.id, created.thread.id, created.message.id,
        )
        return "created"

    async def sync_guild(self, guild_id: int) -> tuple[int, int, int]:
        settings = await asyncio.to_thread(db.get_pc_catalog_settings, guild_id)
        if settings is None or not bool(row_value(settings, "enabled", 0)):
            return 0, 0, 0
        forum_id = row_value(settings, "forum_channel_id")
        if not forum_id:
            return 0, 0, 0
        forum = await self.get_forum(int(forum_id))
        if forum is None:
            raise ValueError("Nastavený kanál není dostupné Discord fórum.")

        found = created = updated = 0
        mention_role_id = row_value(settings, "mention_role_id")
        for source in SOURCES:
            if not self.source_is_enabled(settings, source):
                continue
            products = await self.fetch_source(source)
            found += len(products)
            for product in products:
                result = await self.publish_or_update(
                    guild_id, forum, source, product,
                    int(mention_role_id) if mention_role_id else None,
                )
                if result == "created":
                    created += 1
                else:
                    updated += 1
        return found, created, updated

    async def refresh_from_button(
        self, interaction: discord.Interaction, source: str, build_code: str
    ) -> None:
        if interaction.guild is None or not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message(
                "❌ Sestavy může obnovovat jen správce serveru.", ephemeral=True
            )
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            products = await self.fetch_source(source)
            product = next((item for item in products if item.code == build_code), None)
            if product is None:
                await interaction.followup.send(
                    "⚠️ Sestava už nebyla na webu nalezena. Původní fórum příspěvek jsem nemažal.",
                    ephemeral=True,
                )
                return
            found, created, updated = await self.sync_guild(interaction.guild.id)
            await interaction.followup.send(
                f"✅ Obnoveno. Nalezeno: **{found}**, upraveno: **{updated}**, nové: **{created}**.",
                ephemeral=True,
            )
        except Exception:
            log.exception("Ruční obnovení sestavy selhalo.")
            await interaction.followup.send("❌ Obnovení se nepodařilo. Zkus to prosím později.", ephemeral=True)

    @tasks.loop(minutes=30)
    async def watcher(self) -> None:
        async with self._lock:
            settings = await asyncio.to_thread(db.get_enabled_pc_catalog_settings)
            for row in settings:
                try:
                    await self.sync_guild(int(row["guild_id"]))
                except Exception:
                    log.exception("Automatická kontrola sestav selhala pro server %s.", row["guild_id"])

    @watcher.before_loop
    async def before_watcher(self) -> None:
        await self.bot.wait_until_ready()

    @tasks.loop(seconds=30)
    async def refresh_requests(self) -> None:
        """Provede požadavky z dashboardu bez čekání na běžný interval."""
        async with self._lock:
            requests = await asyncio.to_thread(db.get_pc_catalog_refresh_requests)
            for request in requests:
                guild_id = int(request["guild_id"])
                try:
                    await self.sync_guild(guild_id)
                except Exception:
                    # Požadavek ponecháme pro další pokus, aby se neztratil.
                    log.exception("Obnovení sestav z dashboardu selhalo pro server %s.", guild_id)
                    continue
                await asyncio.to_thread(db.clear_pc_catalog_refresh_request, guild_id)

    @refresh_requests.before_loop
    async def before_refresh_requests(self) -> None:
        await self.bot.wait_until_ready()

    @app_commands.command(name="obnovit", description="Obnoví sledované PC sestavy ve fóru.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def refresh(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            found, created, updated = await self.sync_guild(interaction.guild_id or 0)
            await interaction.followup.send(
                f"✅ Kontrola dokončena. Nalezeno: **{found}**, nové: **{created}**, upraveno: **{updated}**.",
                ephemeral=True,
            )
        except ValueError as error:
            await interaction.followup.send(f"❌ {error}", ephemeral=True)

    @app_commands.command(name="stav", description="Ukáže stav sledování PC sestav.")
    async def status(self, interaction: discord.Interaction) -> None:
        settings = await asyncio.to_thread(db.get_pc_catalog_settings, interaction.guild_id or 0)
        if settings is None or not bool(row_value(settings, "enabled", 0)):
            await interaction.response.send_message("ℹ️ Sledování sestav zde není zapnuté.", ephemeral=True)
            return
        sources = [SOURCES[key][0] for key in SOURCES if self.source_is_enabled(settings, key)]
        await interaction.response.send_message(
            "🖥️ **Sledování sestav je aktivní.**\n"
            f"Zdroje: {', '.join(sources) or 'žádné'}\n"
            f"Fórum: <#{row_value(settings, 'forum_channel_id')}>", ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(PcCatalog(bot))
