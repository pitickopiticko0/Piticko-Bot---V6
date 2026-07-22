from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import AsyncIterator

import discord
from discord import app_commands
from discord.ext import commands, tasks

from services.products.base import Product
from services.products.makejpc import MakeJPCProvider
from utils.database import db
from utils.makejpc_forum_store import makejpc_forum_store
from utils.service_health import mark_error, mark_success


log = logging.getLogger(__name__)

MAKEJPC_FORUM_CHANNEL_ID = int(os.getenv("MAKEJPC_FORUM_CHANNEL_ID", "0"))
MAKEJPC_CHECK_INTERVAL_MINUTES = max(
    5,
    int(os.getenv("MAKEJPC_CHECK_INTERVAL_MINUTES", "15")),
)
MAKEJPC_FIRST_RUN_MODE = os.getenv("MAKEJPC_FIRST_RUN_MODE", "seed").lower().strip()
MAKEJPC_MENTION_ROLE_ID = int(os.getenv("MAKEJPC_MENTION_ROLE_ID", "0"))


class Products(commands.Cog):
    """Automatické sledování a obnovování počítačů na MakejPC."""

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
        return channel if isinstance(channel, discord.ForumChannel) else None

    @staticmethod
    def build_product_embed(product: Product) -> discord.Embed:
        embed = discord.Embed(
            title=product.name,
            url=product.url,
            description="Počítačová sestava z aktuální nabídky MakejPC.",
            color=discord.Color.from_str("#367C2B"),
        )
        embed.add_field(name="💰 Cena", value=product.price, inline=True)
        embed.add_field(
            name="📦 Dostupnost",
            value=product.availability,
            inline=True,
        )
        embed.add_field(name="🔖 Kód", value=product.code, inline=True)
        embed.add_field(
            name="🔗 Detail produktu",
            value=f"[Otevřít na MakejPC]({product.url})",
            inline=False,
        )

        if product.image_url:
            embed.set_image(url=product.image_url)

        embed.set_footer(
            text="MakejPC • automaticky spravováno Piticko Botem"
        )
        return embed

    async def publish_product(
        self,
        forum: discord.ForumChannel,
        product: Product,
    ) -> tuple[discord.Thread, discord.Message]:
        content = None
        allowed_mentions = discord.AllowedMentions.none()

        if MAKEJPC_MENTION_ROLE_ID:
            content = f"<@&{MAKEJPC_MENTION_ROLE_ID}>"
            allowed_mentions = discord.AllowedMentions(roles=True)

        created = await forum.create_thread(
            name=product.thread_name,
            content=content,
            embed=self.build_product_embed(product),
            allowed_mentions=allowed_mentions,
        )

        thread = created.thread
        message = created.message

        await asyncio.to_thread(
            makejpc_forum_store.save,
            product.code,
            forum.id,
            thread.id,
            message.id,
        )
        return thread, message

    async def _iter_forum_threads(
        self,
        forum: discord.ForumChannel,
    ) -> AsyncIterator[discord.Thread]:
        seen: set[int] = set()

        for thread in forum.threads:
            if thread.id not in seen:
                seen.add(thread.id)
                yield thread

        for private in (False, True):
            try:
                async for thread in forum.archived_threads(
                    limit=None,
                    private=private,
                ):
                    if thread.id not in seen:
                        seen.add(thread.id)
                        yield thread
            except (discord.Forbidden, discord.HTTPException):
                if private:
                    continue
                raise

    async def _get_starter_message(
        self,
        thread: discord.Thread,
        message_id: int | None = None,
    ) -> discord.Message | None:
        candidate_ids = []
        if message_id:
            candidate_ids.append(message_id)
        candidate_ids.append(thread.id)

        for candidate_id in dict.fromkeys(candidate_ids):
            try:
                return await thread.fetch_message(candidate_id)
            except (discord.NotFound, discord.Forbidden):
                continue

        try:
            async for message in thread.history(
                limit=10,
                oldest_first=True,
            ):
                if message.author.id == self.bot.user.id and message.embeds:
                    return message
        except discord.HTTPException:
            pass

        return None

    @staticmethod
    def _message_product_code(message: discord.Message) -> str | None:
        for embed in message.embeds:
            for field in embed.fields:
                if field.name == "🔖 Kód":
                    return str(field.value).strip()
        return None

    async def _find_existing_post(
        self,
        forum: discord.ForumChannel,
        product: Product,
    ) -> tuple[discord.Thread, discord.Message] | None:
        mapping = await asyncio.to_thread(
            makejpc_forum_store.get,
            product.code,
        )

        if mapping:
            thread = forum.get_thread(int(mapping["thread_id"]))
            if thread is None:
                try:
                    fetched = await self.bot.fetch_channel(
                        int(mapping["thread_id"])
                    )
                    thread = fetched if isinstance(fetched, discord.Thread) else None
                except (discord.NotFound, discord.Forbidden):
                    thread = None

            if thread:
                message = await self._get_starter_message(
                    thread,
                    int(mapping["message_id"]),
                )
                if message:
                    return thread, message

            await asyncio.to_thread(
                makejpc_forum_store.delete,
                product.code,
            )

        async for thread in self._iter_forum_threads(forum):
            message = await self._get_starter_message(thread)
            if message is None:
                continue

            if self._message_product_code(message) == product.code:
                await asyncio.to_thread(
                    makejpc_forum_store.save,
                    product.code,
                    forum.id,
                    thread.id,
                    message.id,
                )
                return thread, message

        return None

    async def _update_forum_post(
        self,
        thread: discord.Thread,
        message: discord.Message,
        product: Product,
    ) -> bool:
        new_embed = self.build_product_embed(product)
        changed = (
            thread.name != product.thread_name
            or not message.embeds
            or message.embeds[0].to_dict() != new_embed.to_dict()
        )

        if not changed:
            return False

        if thread.archived:
            await thread.edit(archived=False)

        if thread.name != product.thread_name:
            await thread.edit(name=product.thread_name)

        await message.edit(embed=new_embed)

        return True

    async def run_check(
        self,
        *,
        manual: bool = False,
    ) -> tuple[int, int]:
        """Vrátí (nalezeno, nově_odesláno)."""

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

    async def refresh_forum_products(
        self,
    ) -> tuple[int, int, int, int, int]:
        """
        Aktualizuje databázi i existující Discord forum příspěvky.

        Vrátí:
            (nalezeno, změněno, beze_změny, vytvořeno, chyby)
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

            changed = 0
            unchanged = 0
            created = 0
            failed = 0

            for product in products:
                try:
                    existing = await self._find_existing_post(
                        forum,
                        product,
                    )

                    if existing is None:
                        await self.publish_product(forum, product)
                        created += 1
                    else:
                        thread, message = existing
                        was_changed = await self._update_forum_post(
                            thread,
                            message,
                            product,
                        )
                        if was_changed:
                            changed += 1
                        else:
                            unchanged += 1

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

                except Exception:
                    failed += 1
                    log.exception(
                        "Refresh MakejPC produktu selhal: %s (%s)",
                        product.name,
                        product.code,
                    )

            return len(products), changed, unchanged, created, failed

    async def post_all_products(self) -> tuple[int, int]:
        """Odešle všechny aktuální produkty jako nové příspěvky."""

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
                    log.exception(
                        "Nepodařilo se odeslat MakejPC produkt: %s",
                        product.name,
                    )

            return len(products), sent

    @tasks.loop(minutes=15)
    async def check_makejpc(self):
        try:
            found, sent = await self.run_check()
            log.info(
                "MakejPC kontrola dokončena: nalezeno=%s, odesláno=%s.",
                found,
                sent,
            )
            mark_success("makejpc", f"Nalezeno: {found}, odesláno: {sent}")
        except Exception as error:
            mark_error("makejpc", error)
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
        name="makejpc-refresh",
        description="Obnoví všechny MakejPC sestavy i jejich příspěvky ve fóru.",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def makejpc_refresh(
        self,
        interaction: discord.Interaction,
    ):
        await interaction.response.defer(ephemeral=True)

        try:
            found, changed, unchanged, created, failed = (
                await self.refresh_forum_products()
            )
        except Exception as error:
            log.exception("Obnovení MakejPC sestav selhalo.")
            await interaction.followup.send(
                f"❌ Obnovení selhalo: `{error}`",
                ephemeral=True,
            )
            return

        message = (
            "✅ **MakejPC sestavy byly obnoveny.**\n"
            f"Nalezeno sestav: **{found}**\n"
            f"Upraveno ve fóru: **{changed}**\n"
            f"Beze změny: **{unchanged}**\n"
            f"Nově vytvořené příspěvky: **{created}**\n"
            f"Chyby: **{failed}**"
        )
        await interaction.followup.send(message, ephemeral=True)

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

        await interaction.followup.send(
            f"✅ Nalezeno produktů: **{found}**\n"
            f"Odesláno do fóra: **{sent}**",
            ephemeral=True,
        )

    async def _send_command_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
        command_name: str,
    ) -> None:
        original = getattr(error, "original", error)

        if isinstance(original, app_commands.MissingPermissions):
            message = (
                "❌ Tento příkaz vyžaduje oprávnění "
                "**Spravovat server**."
            )
        else:
            log.exception(
                "Chyba příkazu /%s",
                command_name,
                exc_info=error,
            )
            message = "❌ Příkaz se nepodařilo provést."

        try:
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
        except discord.NotFound:
            log.warning(
                "Na Discord interakci %s už nebylo možné odpovědět.",
                interaction.id,
            )

    @makejpc_check.error
    async def makejpc_check_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ):
        await self._send_command_error(
            interaction,
            error,
            "makejpc-kontrola",
        )

    @makejpc_refresh.error
    async def makejpc_refresh_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ):
        await self._send_command_error(
            interaction,
            error,
            "makejpc-refresh",
        )

    @makejpc_post_all.error
    async def makejpc_post_all_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ):
        await self._send_command_error(
            interaction,
            error,
            "makejpc-post-all",
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Products(bot))
