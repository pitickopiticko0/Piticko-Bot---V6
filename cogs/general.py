import discord
from discord import app_commands
from discord.ext import commands
from config import EMBED_COLOR

from utils.embeds import status_embed


class General(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="ping", description="Zobrazí odezvu bota.")
    async def ping(self, interaction: discord.Interaction):
        await interaction.response.send_message(f"🏓 Pong! `{round(self.bot.latency * 1000)} ms`")

    @app_commands.command(name="status", description="Zobrazí stav bota.")
    async def status(self, interaction: discord.Interaction):
        await interaction.response.send_message(embed=status_embed(self.bot))

    @app_commands.command(name="help", description="Zobrazí nápovědu.")
    async def help(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="📖 Nápověda",
            description="Brokes Bot v2 používá pouze slash příkazy.",
            color=EMBED_COLOR,
        )
        embed.add_field(name="/ping", value="Odezva bota", inline=False)
        embed.add_field(name="/status", value="Stav bota", inline=False)
        embed.add_field(name="/youtube add", value="Přidá YouTube kanál pro notifikace", inline=False)
        embed.add_field(name="/youtube remove", value="Odebere sledovaný YouTube kanál", inline=False)
        embed.add_field(name="/youtube list", value="Seznam sledovaných kanálů", inline=False)
        embed.add_field(name="/youtube check", value="Ručně zkontroluje nová videa", inline=False)
        embed.add_field(name="/youtube test", value="Pošle testovací embed", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(General(bot))
