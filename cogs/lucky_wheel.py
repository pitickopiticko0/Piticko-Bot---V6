"""Příkaz otevírající veřejné kolo štěstí pro konkrétní Discord server."""

import discord
from discord import app_commands
from discord.ext import commands

from config import EMBED_COLOR, EMBED_FOOTER
from utils.database import db
from utils.public_urls import lucky_wheel_url


class LuckyWheel(commands.Cog):
    @app_commands.command(
        name="kolo", description="Otevře veřejné kolo štěstí tohoto serveru."
    )
    async def wheel(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "❌ Kolo štěstí lze otevřít pouze přímo na Discord serveru.",
                ephemeral=True,
            )
            return

        url = lucky_wheel_url(interaction.guild.id)
        if not url:
            await interaction.response.send_message(
                "❌ Veřejná adresa dashboardu není nastavená. "
                "Správce musí doplnit `DASHBOARD_PUBLIC_URL`.",
                ephemeral=True,
            )
            return

        db.add_guild(interaction.guild.id, interaction.guild.name)
        embed = discord.Embed(
            title="🎡 Kolo štěstí",
            description=(
                "Otevři veřejné kolo tohoto serveru a zatoč si bez omezení.\n"
                "Výseče upravuje správce serveru v dashboardu."
            ),
            color=EMBED_COLOR,
        )
        embed.set_footer(text=EMBED_FOOTER)
        view = discord.ui.View()
        view.add_item(discord.ui.Button(
            label="Otevřít kolo štěstí", emoji="🎡", url=url
        ))
        await interaction.response.send_message(embed=embed, view=view)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(LuckyWheel())
