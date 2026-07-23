import asyncio
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from services.kick_watcher import KickWatcher
from utils.kick_api import KickAPIError, kick_api
from utils import kick_store


class Kick(commands.GroupCog, group_name="kick"):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.watcher = KickWatcher(bot)

    async def cog_load(self) -> None:
        self.watcher.start()

    async def cog_unload(self) -> None:
        self.watcher.stop()

    @app_commands.command(name="add", description="Přidá Kick streamera do oznámení.")
    @app_commands.describe(streamer="Kick jméno nebo odkaz", kanal="Kanál pro oznámení", role="Role k označení")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def add(self, interaction: discord.Interaction, streamer: str,
                  kanal: discord.TextChannel, role: Optional[discord.Role] = None):
        if interaction.guild is None:
            await interaction.response.send_message("❌ Použij tento příkaz na serveru.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        try:
            channel = await kick_api.get_channel(streamer)
        except KickAPIError as error:
            await interaction.followup.send(f"❌ Kick API chyba: {error}", ephemeral=True)
            return
        if channel is None:
            await interaction.followup.send("❌ Kick streamer nebyl nalezen.", ephemeral=True)
            return
        await asyncio.to_thread(
            kick_store.add, interaction.guild.id, channel.user_id, channel.slug,
            kanal.id, role.id if role else None,
        )
        await interaction.followup.send(
            f"✅ Sleduji **{channel.slug}** a oznámení pošlu do {kanal.mention}.",
            ephemeral=True,
        )

    @app_commands.command(name="remove", description="Odebere Kick streamera.")
    @app_commands.describe(streamer="Kick jméno nebo odkaz")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def remove(self, interaction: discord.Interaction, streamer: str):
        if interaction.guild is None:
            await interaction.response.send_message("❌ Použij tento příkaz na serveru.", ephemeral=True)
            return
        slug = kick_api.normalize_slug(streamer)
        removed = await asyncio.to_thread(kick_store.remove, interaction.guild.id, slug)
        await interaction.response.send_message(
            "✅ Streamer odebrán." if removed else "❌ Streamer nebyl nalezen.", ephemeral=True
        )

    @app_commands.command(name="list", description="Zobrazí sledované Kick streamery.")
    async def list_streamers(self, interaction: discord.Interaction):
        if interaction.guild is None:
            await interaction.response.send_message("❌ Použij tento příkaz na serveru.", ephemeral=True)
            return
        rows = await asyncio.to_thread(kick_store.get_guild, interaction.guild.id)
        text = "\n".join(
            f"• **{row['streamer_slug']}** → <#{row['discord_channel_id']}>"
            for row in rows
        ) or "Žádní sledovaní Kick streameři."
        await interaction.response.send_message(text, ephemeral=True)

    @app_commands.command(name="check", description="Ručně zkontroluje Kick streamy.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def check(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        found, sent = await self.watcher.check_all()
        await interaction.followup.send(
            f"✅ Kontrola dokončena. Živých: {found}, odesláno: {sent}.", ephemeral=True
        )

    async def cog_app_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        original = getattr(error, "original", error)
        message = "❌ Potřebuješ oprávnění **Spravovat server**." if isinstance(
            original, app_commands.MissingPermissions
        ) else f"❌ Kick příkaz selhal: {original}"
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Kick(bot))
