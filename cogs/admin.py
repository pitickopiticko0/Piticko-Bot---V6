import time

import discord
from discord import app_commands
from discord.ext import commands

from config import EMBED_COLOR, EMBED_FOOTER, VERSION
from utils.database import db


START_TIME = time.time()


class Admin(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="stats", description="Zobrazí statistiky bota.")
    async def stats(self, interaction: discord.Interaction):
        data = db.stats()
        uptime_seconds = int(time.time() - START_TIME)
        hours, remainder = divmod(uptime_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)

        embed = discord.Embed(title="📊 Piticko Bot statistiky", color=EMBED_COLOR)
        embed.add_field(name="🌐 Servery", value=str(len(self.bot.guilds)), inline=True)
        embed.add_field(name="📺 YouTube kanály", value=str(data["youtube_channels"]), inline=True)
        embed.add_field(name="🔔 Odběry", value=str(data["subscriptions"]), inline=True)
        embed.add_field(name="🎬 Uložená videa", value=str(data["videos"]), inline=True)
        embed.add_field(name="⏱️ Uptime", value=f"{hours}h {minutes}m {seconds}s", inline=True)
        embed.add_field(name="🧩 Verze", value=VERSION, inline=True)
        embed.set_footer(text=EMBED_FOOTER)

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="dashboard", description="Zobrazí přehled stavu bota.")
    async def dashboard(self, interaction: discord.Interaction):
        data = db.stats()
        uptime_seconds = int(time.time() - START_TIME)
        hours, remainder = divmod(uptime_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)

        embed = discord.Embed(
            title="📊 Piticko Bot Dashboard",
            description="Přehled aktuálního stavu bota.",
            color=EMBED_COLOR,
        )

        embed.add_field(name="🌐 Servery", value=str(len(self.bot.guilds)), inline=True)
        embed.add_field(name="📺 YouTube kanály", value=str(data["youtube_channels"]), inline=True)
        embed.add_field(name="🔔 Aktivní odběry", value=str(data["subscriptions"]), inline=True)
        embed.add_field(name="🎬 Uložená videa", value=str(data["videos"]), inline=True)
        embed.add_field(name="🟢 Watcher", value="Běží", inline=True)
        embed.add_field(name="⏱️ Uptime", value=f"{hours}h {minutes}m {seconds}s", inline=True)
        embed.add_field(name="🧩 Verze", value=VERSION, inline=True)
        embed.add_field(name="📡 Latence", value=f"{round(self.bot.latency * 1000)} ms", inline=True)
        embed.add_field(name="💾 Databáze", value="SQLite", inline=True)

        embed.set_footer(text=EMBED_FOOTER)

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="about", description="Informace o botovi.")
    async def about(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="🍺 Piticko Bot",
            description="Discord YouTube notification bot.",
            color=EMBED_COLOR,
        )

        embed.add_field(name="Verze", value=VERSION, inline=True)
        embed.add_field(name="Framework", value="discord.py", inline=True)
        embed.add_field(name="Databáze", value="SQLite", inline=True)
        embed.set_footer(text=EMBED_FOOTER)

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="health", description="Zkontroluje stav bota.")
    async def health(self, interaction: discord.Interaction):
        try:
            db.stats()
            database_status = "🟢 OK"
        except Exception:
            database_status = "🔴 Chyba"

        embed = discord.Embed(title="🩺 Health Check", color=EMBED_COLOR)
        embed.add_field(name="Discord", value="🟢 OK", inline=False)
        embed.add_field(name="SQLite", value=database_status, inline=False)
        embed.add_field(name="Ping", value=f"{round(self.bot.latency * 1000)} ms", inline=False)
        embed.set_footer(text=EMBED_FOOTER)

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="sync", description="Znovu synchronizuje slash příkazy.")
    @app_commands.checks.has_permissions(administrator=True)
    async def sync(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        synced = await self.bot.tree.sync()

        await interaction.followup.send(
            f"✅ Synchronizováno **{len(synced)}** slash příkazů.",
            ephemeral=True,
        )

    async def cog_app_command_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ):
        if isinstance(error, app_commands.MissingPermissions):
            message = "❌ Tento příkaz může použít pouze administrátor."
        else:
            message = f"❌ Chyba: `{error}`"

        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Admin(bot))
