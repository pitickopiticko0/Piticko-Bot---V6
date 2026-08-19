import discord
from discord import app_commands
from discord.ext import commands
from config import EMBED_COLOR

from utils.embeds import status_embed
from utils.support import get_support_url


class General(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="ping", description="Zobrazí odezvu bota.")
    async def ping(self, interaction: discord.Interaction):
        await interaction.response.send_message(f"🏓 Pong! `{round(self.bot.latency * 1000)} ms`")

    @app_commands.command(name="status", description="Zobrazí stav bota.")
    async def status(self, interaction: discord.Interaction):
        await interaction.response.send_message(embed=status_embed(self.bot))

    @app_commands.command(
        name="podpora", description="Zobrazí možnosti dobrovolné podpory bota."
    )
    async def support(self, interaction: discord.Interaction):
        support_url = get_support_url()
        if not support_url:
            await interaction.response.send_message(
                "ℹ️ Odkaz pro podporu zatím není nastavený.", ephemeral=True
            )
            return

        embed = discord.Embed(
            title="❤️ Podpoř Piticko Bota",
            description=(
                "Líbí se ti bot? Dobrovolnou podporou pomůžeš s úhradou "
                "hostingu a dalším vývojem.\n\n"
                "Podpora neposkytuje žádnou herní ani moderátorskou výhodu."
            ),
            color=EMBED_COLOR,
        )
        view = discord.ui.View()
        view.add_item(discord.ui.Button(
            label="Podpořit bota", emoji="❤️", url=support_url,
        ))
        await interaction.response.send_message(embed=embed, view=view)

    @app_commands.command(name="help", description="Zobrazí nápovědu.")
    async def help(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="📖 Nápověda",
            description="Piticko Bot používá slash příkazy.",
            color=EMBED_COLOR,
        )
        embed.add_field(name="/ping", value="Odezva bota", inline=False)
        embed.add_field(name="/status", value="Stav bota", inline=False)
        embed.add_field(name="/podpora", value="Dobrovolná podpora provozu bota", inline=False)
        embed.add_field(name="/youtube add", value="Přidá YouTube kanál pro notifikace", inline=False)
        embed.add_field(name="/youtube remove", value="Odebere sledovaný YouTube kanál", inline=False)
        embed.add_field(name="/youtube list", value="Seznam sledovaných kanálů", inline=False)
        embed.add_field(name="/youtube check", value="Ručně zkontroluje nová videa", inline=False)
        embed.add_field(name="/youtube test", value="Pošle testovací embed", inline=False)
        embed.add_field(
            name="/alzadny-kontrola",
            value="Bezpečně otestuje relevantní AlzaDny nabídky",
            inline=False,
        )
        embed.add_field(
            name="/diagnostika server",
            value="Administrátorům zkontroluje nastavení a oprávnění modulů",
            inline=False,
        )
        embed.add_field(
            name="/diagnostika kanal",
            value="Administrátorům ukáže oprávnění bota ve vybraném kanálu",
            inline=False,
        )
        embed.add_field(
            name="/ovecky stav · /ovecky zebricek",
            value="Stav a žebříček komunitního počítání oveček",
            inline=False,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(General(bot))
