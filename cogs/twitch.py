import asyncio

import discord
from discord import app_commands
from discord.ext import commands

from services.twitch_watcher import TwitchWatcher, build_twitch_embed
from utils.twitch_api import TwitchAPIError, twitch_api
from utils.twitch_store import twitch_store


class Twitch(commands.GroupCog, group_name="twitch"):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.watcher = TwitchWatcher(bot)

    async def cog_load(self) -> None:
        self.watcher.start()

    async def cog_unload(self) -> None:
        self.watcher.stop()

    @app_commands.command(name="add", description="Přidá Twitch streamera do oznámení.")
    @app_commands.describe(streamer="Twitch login nebo odkaz", kanal="Kanál pro oznámení", role="Role k označení")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def add(self, interaction: discord.Interaction, streamer: str,
                  kanal: discord.TextChannel, role: discord.Role | None = None) -> None:
        if interaction.guild is None:
            await interaction.response.send_message("❌ Použij tento příkaz na serveru.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        try:
            user = await twitch_api.get_user(streamer)
        except TwitchAPIError as error:
            await interaction.followup.send(f"❌ Twitch API chyba: {error}", ephemeral=True)
            return
        if user is None:
            await interaction.followup.send("❌ Twitch streamer nebyl nalezen.", ephemeral=True)
            return
        await asyncio.to_thread(
            twitch_store.add_subscription,
            interaction.guild.id, user.id, user.login, user.display_name,
            kanal.id, role.id if role else None, user.profile_image_url,
        )
        await interaction.followup.send(
            f"✅ Sleduji **{user.display_name}**. Oznámení půjdou do {kanal.mention}.",
            ephemeral=True,
        )

    @app_commands.command(name="remove", description="Odebere Twitch streamera z oznámení.")
    @app_commands.describe(streamer="Twitch login streamera")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def remove(self, interaction: discord.Interaction, streamer: str) -> None:
        if interaction.guild is None:
            await interaction.response.send_message("❌ Použij tento příkaz na serveru.", ephemeral=True)
            return
        login = twitch_api.normalize_login(streamer)
        removed = await asyncio.to_thread(twitch_store.remove_subscription, interaction.guild.id, login)
        await interaction.response.send_message(
            f"✅ Streamer **{login}** byl odebrán." if removed else f"❌ Streamer **{login}** není v seznamu.",
            ephemeral=True,
        )

    @app_commands.command(name="list", description="Zobrazí sledované Twitch streamery.")
    async def list_subscriptions(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message("❌ Použij tento příkaz na serveru.", ephemeral=True)
            return
        rows = await asyncio.to_thread(twitch_store.get_guild_subscriptions, interaction.guild.id)
        if not rows:
            await interaction.response.send_message("📭 Zatím nesleduješ žádné Twitch streamery.", ephemeral=True)
            return
        lines = []
        for row in rows:
            role = f"<@&{row['mention_role_id']}>" if row["mention_role_id"] else "bez role"
            lines.append(f"• **{row['streamer_name']}** (`{row['streamer_login']}`) → <#{row['discord_channel_id']}> • {role}")
        embed = discord.Embed(
            title="🟣 Sledovaní Twitch streameři",
            description="\n".join(lines),
            color=discord.Color.from_rgb(145, 70, 255),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="check", description="Ručně zkontroluje Twitch streamy.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def check(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        found, sent = await self.watcher.check_all()
        await interaction.followup.send(
            f"✅ Kontrola dokončena.\nNové streamy: **{found}**\nOdesláno: **{sent}**",
            ephemeral=True,
        )

    @app_commands.command(name="test", description="Pošle testovací oznámení aktivního streamu.")
    @app_commands.describe(streamer="Twitch login nebo odkaz", kanal="Kanál pro test", role="Volitelná role")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def test(self, interaction: discord.Interaction, streamer: str,
                   kanal: discord.TextChannel, role: discord.Role | None = None) -> None:
        await interaction.response.defer(ephemeral=True)
        try:
            user = await twitch_api.get_user(streamer)
            stream = await twitch_api.get_stream(streamer)
        except TwitchAPIError as error:
            await interaction.followup.send(f"❌ Twitch API chyba: {error}", ephemeral=True)
            return
        if user is None:
            await interaction.followup.send("❌ Twitch streamer nebyl nalezen.", ephemeral=True)
            return
        if stream is None:
            await interaction.followup.send(f"ℹ️ **{user.display_name}** právě nevysílá.", ephemeral=True)
            return
        await kanal.send(
            content=role.mention if role else None,
            embed=build_twitch_embed(stream, user.profile_image_url),
            allowed_mentions=discord.AllowedMentions(roles=True, users=False, everyone=False),
        )
        await interaction.followup.send(f"✅ Test byl poslán do {kanal.mention}.", ephemeral=True)

    async def cog_app_command_error(self, interaction: discord.Interaction,
                                    error: app_commands.AppCommandError) -> None:
        original = getattr(error, "original", error)
        message = "❌ Potřebuješ oprávnění **Spravovat server**." if isinstance(
            original, app_commands.MissingPermissions
        ) else f"❌ Twitch příkaz selhal: {original}"
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Twitch(bot))
