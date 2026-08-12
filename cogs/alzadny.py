from __future__ import annotations

import logging
import os

import discord
from discord import app_commands
from discord.ext import commands

from services.products.alzadny import AlzaDaysProvider, AlzaDeal


log = logging.getLogger(__name__)
ALZADNY_MIN_DISCOUNT = max(
    5,
    min(int(os.getenv("ALZADNY_MIN_DISCOUNT", "15")), 90),
)


class AlzaDays(commands.Cog):
    """Bezpečná diagnostika nabídek AlzaDny před zapnutím watcheru."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.provider = AlzaDaysProvider(ALZADNY_MIN_DISCOUNT)

    @staticmethod
    def build_embed(deal: AlzaDeal) -> discord.Embed:
        embed = discord.Embed(
            title=deal.name,
            url=deal.url,
            description=(
                f"**Sleva {deal.discount_percent} %** s kódem "
                f"`{deal.coupon}`"
            ),
            color=discord.Color.from_str("#00A42E"),
        )
        embed.add_field(name="Akční cena", value=deal.price, inline=True)
        embed.add_field(
            name="Původní cena",
            value=deal.original_price,
            inline=True,
        )
        embed.add_field(name="Dostupnost", value=deal.availability, inline=True)
        embed.add_field(name="Kategorie", value=deal.category, inline=True)
        embed.add_field(name="Kód produktu", value=f"`{deal.code}`", inline=True)
        if deal.image_url:
            embed.set_thumbnail(url=deal.image_url)
        embed.set_footer(text="Diagnostika AlzaDny • nic nebylo zveřejněno")
        return embed

    @app_commands.command(
        name="alzadny-kontrola",
        description="Otestuje relevantní AlzaDny nabídky bez veřejného odeslání.",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def check(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)

        try:
            deals = await self.provider.fetch_deals()
        except Exception as error:
            log.exception("Diagnostika AlzaDny selhala.")
            await interaction.followup.send(
                f"❌ AlzaDny kontrola selhala: `{error}`",
                ephemeral=True,
            )
            return

        if not deals:
            diagnostic_lines = []
            for item in self.provider.last_diagnostics:
                status = str(item.status_code) if item.status_code else "chyba"
                diagnostic_lines.append(
                    f"• **{item.category}**: HTTP {status}, "
                    f"{item.response_bytes // 1024} kB, karty {item.cards_found}, "
                    f"kupóny {item.coupons_found}, přijato {item.deals_accepted}"
                    + (f" (`{item.error}`)" if item.error else "")
                )
            diagnostics = "\n".join(diagnostic_lines) or "• Žádný zdroj nebyl zpracován."
            await interaction.followup.send(
                "⚠️ Parser nenašel žádné relevantní AlzaDny nabídky. "
                "Automatické odesílání proto zatím nezapínej.\n\n"
                f"**Diagnostika zdrojů**\n{diagnostics}",
                ephemeral=True,
            )
            return

        preview = deals[:5]
        await interaction.followup.send(
            f"✅ Nalezeno **{len(deals)}** relevantních nabídek se slevou "
            f"alespoň **{ALZADNY_MIN_DISCOUNT} %**. Zobrazuji prvních "
            f"**{len(preview)}**; nic nebylo zveřejněno.",
            embeds=[self.build_embed(deal) for deal in preview],
            ephemeral=True,
        )

    @check.error
    async def check_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        if isinstance(error, app_commands.MissingPermissions):
            message = "❌ Příkaz vyžaduje oprávnění **Spravovat server**."
        else:
            log.exception("Chyba příkazu /alzadny-kontrola", exc_info=error)
            message = "❌ Kontrolu AlzaDny se nepodařilo spustit."

        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AlzaDays(bot))
