from __future__ import annotations

import asyncio
import logging
import os

import discord
from discord import app_commands
from discord.ext import commands, tasks

from services.products.base import Product
from services.products.makejpc import MakeJPCProvider
from utils.database import db


log = logging.getLogger(__name__)

MAKEJPC_FORUM_CHANNEL_ID = int(os.getenv("MAKEJPC_FORUM_CHANNEL_ID", "0"))
MAKEJPC_CHECK_INTERVAL_MINUTES = max(
    5,
    int(os.getenv("MAKEJPC_CHECK_INTERVAL_MINUTES", "15")),
)
MAKEJPC_FIRST_RUN_MODE = os.getenv("MAKEJPC_FIRST_RUN_MODE", "seed").lower().strip()
MAKEJPC_MENTION_ROLE_ID = int(os.getenv("MAKEJPC_MENTION_ROLE_ID", "0"))


class Products(commands.Cog):
    """Automatické sledování nových počítačů na MakejPC."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.provider = MakeJPCProvider()
        self._run_lock = asyncio.Lock()

        self.check_makejpc.change_interval(
            minutes=MAKEJPC_CHECK_INTERVAL_MINUTES
        )
        self.check_makejpc.start()

    def cog_unload(self):
        self.check_makejpc.cancel()

    def get_forum(self) -> discord.ForumChannel | None:
        channel = self.bot.get_channel(MAKEJPC_FORUM_CHANNEL_ID)

        if isinstance(channel, discord.ForumChannel):
            return channel

        return None

    async def publish_product(
        self,
        forum: discord.ForumChannel,
        product: Product,
    ) -> None:
        embed = discord.Embed(
            title=product.name,
            url=product.url,
            description="Nový počítač byl přidán do nabídky MakejPC.",
            color=discord.Color.from_str("#367C2B"),
        )

        embed.add_field(
            name="💰 Cena",
            value=product.price,
            inline=True,
        )
        embed.add_field(
            name="📦 Dostupnost",
            value=product.availability,
            inline=True,
        )
        embed.add_field(
            name="🔖 Kód",
            value=product.code,
            inline=True,
        )
        embed.add_field(
            name="🔗 Detail produktu",
            value=f"[Otevřít na MakejPC]({product.url})",
            inline=False,
        )

        if product.image_url:
            embed.set_image(url=product.image_url)

        embed.set_footer(
            text="MakejPC • automaticky odesláno Piticko Botem"
        )

        content = None
        allowed_mentions = discord.AllowedMentions.none()

        if MAKEJPC_MENTION_ROLE_ID:
            content = f"<@&{MAKEJPC_MENTION_ROLE_ID}>"
            allowed_mentions = discord.AllowedMentions(roles=True)

        await forum.create_thread(
            name=product.thread_name,
            content=content,
            embed=embed,
            allowed_mentions=allowed_mentions,
        )

    async def run_check(
        self,
        *,
        manual: bool = False,
    ) -> tuple[int, int]:
        """Vrátí (nalezeno, odesláno)."""

        if self._run_lock.locked():
            return 0, 0

        async with self._run_lock:
            forum = self.get_forum()

            if forum is None:
                raise RuntimeError(
                    "MAKEJPC_FORUM_CHANNEL_ID neukazuje "
                    "na Discord forum kanál."
                )

            products = await self.provider.fetch_products()

            if not products:
                raise RuntimeError(
                    "MakejPC parser nenašel žádné produkty."
                )

            known_count = db.count_makejpc_products()

            if (
                known_count == 0
                and MAKEJPC_FIRST_RUN_MODE != "post_all"
                and not manual
            ):
                for product in products:
                    db.add_makejpc_product(
                        product.code,
                        product.name,
                        product.price,
                        product.availability,
                        product.url,
                        product.image_url,
                        announced=False,
                    )

                log.info(
                    "MakejPC inicializace: uloženo %s existujících "
                    "produktů bez odeslání.",
                    len(products),
                )

                return len(products), 0

            sent = 0

            for product in reversed(products):
                if db.makejpc_product_exists(product.code):
                    db.update_makejpc_product(
                        product.code,
                        product.name,
                        product.price,
                        product.availability,
                        product.url,
                        product.image_url,
                    )
                    continue

                await self.publish_product(forum, product)

                db.add_makejpc_product(
                    product.code,
                    product.name,
                    product.price,
                    product.availability,
                    product.url,
                    product.image_url,
                    announced=True,
                )

                sent += 1

            return len(products), sent

    async def post_all_products(self) -> tuple[int, int]:
        """
        Odešle všechny aktuální produkty bez ohledu na stav databáze.

        Vrátí:
            (nalezeno, úspěšně odesláno)
        """

        if self._run_lock.locked():
            raise RuntimeError(
                "Právě probíhá jiná MakejPC kontrola. "
                "Zkus příkaz za chvíli znovu."
            )

        async with self._run_lock:
            forum = self.get_forum()

            if forum is None:
                raise RuntimeError(
                    "MAKEJPC_FORUM_CHANNEL_ID neukazuje "
                    "na Discord forum kanál."
                )

            products = await self.provider.fetch_products()

            if not products:
                raise RuntimeError(
                    "MakejPC parser nenašel žádné produkty."
                )

            sent = 0
            failed = 0

            for product in reversed(products):
                try:
                    await self.publish_product(forum, product)

                    if db.makejpc_product_exists(product.code):
                        db.update_makejpc_product(
                            product.code,
                            product.name,
                            product.price,
                            product.availability,
                            product.url,
                            product.image_url,
                        )
                    else:
                        db.add_makejpc_product(
                            product.code,
                            product.name,
                            product.price,
                            product.availability,
                            product.url,
                            product.image_url,
                            announced=True,
                        )

                    sent += 1

                except Exception:
                    failed += 1
                    log.exception(
                        "Nepodařilo se odeslat MakejPC produkt: %s",
                        product.name,
                    )

            if sent == 0 and failed > 0:
                raise RuntimeError(
                    f"Nepodařilo se odeslat žádný produkt. "
                    f"Počet chyb: {failed}."
                )

            return len(products), sent

    @tasks.loop(minutes=15)
    async def check_makejpc(self):
        try:
            found, sent = await self.run_check()

            log.info(
                "MakejPC kontrola dokončena: "
                "nalezeno=%s, odesláno=%s.",
                found,
                sent,
            )

        except Exception:
            log.exception("MakejPC kontrola selhala.")

    @check_makejpc.before_loop
    async def before_check_makejpc(self):
        await self.bot.wait_until_ready()

    @app_commands.command(
        name="makejpc-kontrola",
        description="Ručně zkontroluje nové počítače na MakejPC.",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def makejpc_check(
        self,
        interaction: discord.Interaction,
    ):
        await interaction.response.defer(ephemeral=True)

        try:
            found, sent = await self.run_check(manual=True)

        except Exception as error:
            log.exception("Ruční MakejPC kontrola selhala.")

            await interaction.followup.send(
                f"❌ Kontrola selhala: `{error}`",
                ephemeral=True,
            )
            return

        await interaction.followup.send(
            f"✅ Nalezeno produktů: **{found}**\n"
            f"Nově odesláno do fóra: **{sent}**",
            ephemeral=True,
        )

    @app_commands.command(
        name="makejpc-post-all",
        description="Odešle všechny aktuální sestavy z MakejPC do fóra.",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def makejpc_post_all(
        self,
        interaction: discord.Interaction,
    ):
        await interaction.response.defer(ephemeral=True)

        try:
            found, sent = await self.post_all_products()

        except Exception as error:
            log.exception(
                "Hromadné odeslání MakejPC produktů selhalo."
            )

            await interaction.followup.send(
                f"❌ Odesílání selhalo: `{error}`",
                ephemeral=True,
            )
            return

        failed = found - sent

        message = (
            f"✅ Nalezeno produktů: **{found}**\n"
            f"Odesláno do fóra: **{sent}**"
        )

        if failed > 0:
            message += f"\nNepodařilo se odeslat: **{failed}**"

        await interaction.followup.send(
            message,
            ephemeral=True,
        )

    @makejpc_check.error
    async def makejpc_check_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ):
        if isinstance(error, app_commands.MissingPermissions):
            message = (
                "❌ Tento příkaz vyžaduje oprávnění "
                "**Spravovat server**."
            )
        else:
            log.exception(
                "Chyba příkazu /makejpc-kontrola",
                exc_info=error,
            )
            message = "❌ Příkaz se nepodařilo provést."

        if interaction.response.is_done():
            await interaction.followup.send(
                message,
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                message,
                ephemeral=True,
            )

    @makejpc_post_all.error
    async def makejpc_post_all_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ):
        if isinstance(error, app_commands.MissingPermissions):
            message = (
                "❌ Tento příkaz vyžaduje oprávnění "
                "**Spravovat server**."
            )
        else:
            log.exception(
                "Chyba příkazu /makejpc-post-all",
                exc_info=error,
            )
            message = "❌ Příkaz se nepodařilo provést."

        if interaction.response.is_done():
            await interaction.followup.send(
                message,
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                message,
                ephemeral=True,
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(Products(bot))
