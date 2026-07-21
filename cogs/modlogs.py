from __future__ import annotations

from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from config import EMBED_COLOR, EMBED_FOOTER
from utils.database import db
from utils.logger import logger


class ModLogs(commands.GroupCog, name="modlogs"):
    """Moderační logy pro důležité události na serveru."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def safe_defer(
        self,
        interaction: discord.Interaction,
    ) -> bool:
        try:
            await interaction.response.defer(ephemeral=True)
            return True

        except discord.NotFound:
            logger.warning(
                "Modlogs interakce %s vypršela nebo už není dostupná.",
                interaction.id,
            )
            return False

        except discord.HTTPException as error:
            logger.warning(
                "Nepodařilo se potvrdit modlogs interakci %s: %s",
                interaction.id,
                error,
            )
            return False

    def get_settings(self, guild_id: int):
        return db.get_modlog_settings(guild_id)

    def save_settings(self, guild_id: int, channel_id: int) -> None:
        current = db.get_modlog_settings(guild_id)
        values = {}
        if current is not None:
            values = {
                name: bool(current[name])
                for name in (
                    "log_members",
                    "log_messages",
                    "log_voice",
                    "log_channels",
                    "log_bans",
                )
            }
        db.set_modlog_settings(
            guild_id,
            channel_id,
            enabled=True,
            **values,
        )

    def disable_settings(self, guild_id: int) -> None:
        db.set_modlog_enabled(guild_id, False)

    async def get_log_channel(
        self,
        guild: discord.Guild,
        event_group: str,
    ) -> Optional[discord.TextChannel]:
        try:
            settings = self.get_settings(guild.id)
        except Exception:
            logger.exception(
                "Nepodařilo se načíst modlog nastavení pro server %s.",
                guild.id,
            )
            return None

        if settings is None or not settings["enabled"]:
            return None

        group_column = {
            "members": "log_members",
            "messages": "log_messages",
            "voice": "log_voice",
            "channels": "log_channels",
            "bans": "log_bans",
        }.get(event_group)

        if group_column and not settings[group_column]:
            return None

        channel_id = int(settings["channel_id"])
        channel = guild.get_channel(channel_id)

        if isinstance(channel, discord.TextChannel):
            return channel

        try:
            fetched = await guild.fetch_channel(channel_id)

            if isinstance(fetched, discord.TextChannel):
                return fetched

        except discord.NotFound:
            logger.warning(
                "Modlog kanál %s nebyl nalezen na serveru %s.",
                channel_id,
                guild.id,
            )

        except discord.Forbidden:
            logger.warning(
                "Bot nemá oprávnění načíst modlog kanál %s.",
                channel_id,
            )

        except discord.HTTPException:
            logger.exception(
                "Discord chyba při načítání modlog kanálu %s.",
                channel_id,
            )

        return None

    async def send_log(
        self,
        guild: discord.Guild,
        event_group: str,
        embed: discord.Embed,
    ) -> None:
        channel = await self.get_log_channel(guild, event_group)

        if channel is None:
            return

        embed.set_footer(text=EMBED_FOOTER)
        embed.timestamp = discord.utils.utcnow()

        try:
            await channel.send(embed=embed)

        except discord.Forbidden:
            logger.warning(
                "Bot nemá oprávnění poslat modlog do kanálu %s.",
                channel.id,
            )

        except discord.HTTPException:
            logger.exception(
                "Nepodařilo se odeslat modlog do kanálu %s.",
                channel.id,
            )

    @app_commands.command(
        name="setup",
        description="Nastaví kanál pro moderační logy.",
    )
    @app_commands.describe(
        channel="Kanál, kam bude bot posílat moderační logy",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def setup(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
    ):
        if not await self.safe_defer(interaction):
            return

        if interaction.guild is None:
            await interaction.followup.send(
                "❌ Tento příkaz lze použít pouze na serveru.",
                ephemeral=True,
            )
            return

        bot_member = interaction.guild.me

        if bot_member is None:
            await interaction.followup.send(
                "❌ Nepodařilo se načíst účet bota.",
                ephemeral=True,
            )
            return

        permissions = channel.permissions_for(bot_member)

        if not permissions.view_channel or not permissions.send_messages:
            await interaction.followup.send(
                "❌ Bot v tomto kanálu nemá oprávnění **Zobrazit kanál** "
                "a **Posílat zprávy**.",
                ephemeral=True,
            )
            return

        if not permissions.embed_links:
            await interaction.followup.send(
                "❌ Bot v tomto kanálu nemá oprávnění **Vkládat odkazy**.",
                ephemeral=True,
            )
            return

        db.add_guild(
            interaction.guild.id,
            interaction.guild.name,
        )

        self.save_settings(
            interaction.guild.id,
            channel.id,
        )

        embed = discord.Embed(
            title="✅ Moderační logy nastaveny",
            description=(
                "Bot bude do vybraného kanálu zapisovat důležité "
                "události na serveru."
            ),
            color=EMBED_COLOR,
        )

        embed.add_field(
            name="Log kanál",
            value=channel.mention,
            inline=False,
        )

        embed.add_field(
            name="Aktivní logy",
            value=(
                "👤 Členové\n"
                "💬 Zprávy\n"
                "🔊 Voice\n"
                "📝 Kanály\n"
                "🔨 Bany"
            ),
            inline=False,
        )

        embed.set_footer(text=EMBED_FOOTER)

        await interaction.followup.send(
            embed=embed,
            ephemeral=True,
        )

    @app_commands.command(
        name="info",
        description="Zobrazí aktuální nastavení moderačních logů.",
    )
    async def info(self, interaction: discord.Interaction):
        if not await self.safe_defer(interaction):
            return

        if interaction.guild is None:
            await interaction.followup.send(
                "❌ Tento příkaz lze použít pouze na serveru.",
                ephemeral=True,
            )
            return

        settings = self.get_settings(interaction.guild.id)

        if settings is None:
            await interaction.followup.send(
                "📭 Moderační logy zatím nejsou nastavené.",
                ephemeral=True,
            )
            return

        channel = interaction.guild.get_channel(
            int(settings["channel_id"])
        )

        embed = discord.Embed(
            title="📜 Moderační logy",
            color=EMBED_COLOR,
        )

        embed.add_field(
            name="Stav",
            value="🟢 Zapnuto" if settings["enabled"] else "🔴 Vypnuto",
            inline=True,
        )

        embed.add_field(
            name="Kanál",
            value=channel.mention if channel else "Nenalezen",
            inline=True,
        )

        embed.add_field(
            name="Členové",
            value="✅" if settings["log_members"] else "❌",
            inline=True,
        )

        embed.add_field(
            name="Zprávy",
            value="✅" if settings["log_messages"] else "❌",
            inline=True,
        )

        embed.add_field(
            name="Voice",
            value="✅" if settings["log_voice"] else "❌",
            inline=True,
        )

        embed.add_field(
            name="Kanály",
            value="✅" if settings["log_channels"] else "❌",
            inline=True,
        )

        embed.add_field(
            name="Bany",
            value="✅" if settings["log_bans"] else "❌",
            inline=True,
        )

        embed.set_footer(text=EMBED_FOOTER)

        await interaction.followup.send(
            embed=embed,
            ephemeral=True,
        )

    @app_commands.command(
        name="disable",
        description="Vypne moderační logy.",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def disable(self, interaction: discord.Interaction):
        if not await self.safe_defer(interaction):
            return

        if interaction.guild is None:
            await interaction.followup.send(
                "❌ Tento příkaz lze použít pouze na serveru.",
                ephemeral=True,
            )
            return

        self.disable_settings(interaction.guild.id)

        await interaction.followup.send(
            "✅ Moderační logy byly vypnuty.",
            ephemeral=True,
        )

    @app_commands.command(
        name="test",
        description="Pošle testovací zprávu do modlog kanálu.",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def test(self, interaction: discord.Interaction):
        if not await self.safe_defer(interaction):
            return

        if interaction.guild is None:
            await interaction.followup.send(
                "❌ Tento příkaz lze použít pouze na serveru.",
                ephemeral=True,
            )
            return

        channel = await self.get_log_channel(
            interaction.guild,
            "members",
        )

        if channel is None:
            await interaction.followup.send(
                "❌ Modlog kanál nebyl nalezen nebo jsou logy vypnuté.",
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title="🧪 Test moderačních logů",
            description=(
                "Pokud tuto zprávu vidíš, moderační logy jsou "
                "správně nastavené."
            ),
            color=EMBED_COLOR,
        )

        embed.add_field(
            name="Spustil",
            value=interaction.user.mention,
            inline=True,
        )

        embed.add_field(
            name="Server",
            value=interaction.guild.name,
            inline=True,
        )

        await self.send_log(
            interaction.guild,
            "members",
            embed,
        )

        await interaction.followup.send(
            f"✅ Testovací log byl odeslán do {channel.mention}.",
            ephemeral=True,
        )

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        embed = discord.Embed(
            title="📥 Člen se připojil",
            color=EMBED_COLOR,
        )

        embed.set_thumbnail(url=member.display_avatar.url)

        embed.add_field(
            name="Uživatel",
            value=f"{member.mention}\n`{member.id}`",
            inline=False,
        )

        embed.add_field(
            name="Účet vytvořen",
            value=discord.utils.format_dt(
                member.created_at,
                style="R",
            ),
            inline=True,
        )

        embed.add_field(
            name="Počet členů",
            value=str(member.guild.member_count or 0),
            inline=True,
        )

        await self.send_log(
            member.guild,
            "members",
            embed,
        )

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        roles = [
            role.mention
            for role in member.roles
            if not role.is_default()
        ]

        embed = discord.Embed(
            title="📤 Člen odešel",
            color=EMBED_COLOR,
        )

        embed.set_thumbnail(url=member.display_avatar.url)

        embed.add_field(
            name="Uživatel",
            value=f"{member}\n`{member.id}`",
            inline=False,
        )

        embed.add_field(
            name="Role",
            value=", ".join(roles[-15:]) if roles else "Žádné",
            inline=False,
        )

        embed.add_field(
            name="Počet členů",
            value=str(member.guild.member_count or 0),
            inline=True,
        )

        await self.send_log(
            member.guild,
            "members",
            embed,
        )

    @commands.Cog.listener()
    async def on_member_update(
        self,
        before: discord.Member,
        after: discord.Member,
    ):
        if before.nick != after.nick:
            embed = discord.Embed(
                title="✏️ Změna přezdívky",
                color=EMBED_COLOR,
            )

            embed.add_field(
                name="Uživatel",
                value=f"{after.mention}\n`{after.id}`",
                inline=False,
            )

            embed.add_field(
                name="Předtím",
                value=before.nick or before.name,
                inline=True,
            )

            embed.add_field(
                name="Potom",
                value=after.nick or after.name,
                inline=True,
            )

            await self.send_log(
                after.guild,
                "members",
                embed,
            )

        before_roles = set(before.roles)
        after_roles = set(after.roles)

        added = [
            role.mention
            for role in after_roles - before_roles
            if not role.is_default()
        ]

        removed = [
            role.mention
            for role in before_roles - after_roles
            if not role.is_default()
        ]

        if added or removed:
            embed = discord.Embed(
                title="🎭 Změna rolí člena",
                color=EMBED_COLOR,
            )

            embed.add_field(
                name="Uživatel",
                value=f"{after.mention}\n`{after.id}`",
                inline=False,
            )

            if added:
                embed.add_field(
                    name="Přidáno",
                    value=", ".join(added),
                    inline=False,
                )

            if removed:
                embed.add_field(
                    name="Odebráno",
                    value=", ".join(removed),
                    inline=False,
                )

            await self.send_log(
                after.guild,
                "members",
                embed,
            )

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if message.guild is None or message.author.bot:
            return

        content = message.content.strip() if message.content else ""

        embed = discord.Embed(
            title="🗑️ Zpráva smazána",
            color=EMBED_COLOR,
        )

        embed.add_field(
            name="Autor",
            value=f"{message.author.mention}\n`{message.author.id}`",
            inline=True,
        )

        embed.add_field(
            name="Kanál",
            value=message.channel.mention,
            inline=True,
        )

        embed.add_field(
            name="Obsah",
            value=content[:1000] if content else "*Obsah nebyl dostupný.*",
            inline=False,
        )

        if message.attachments:
            attachments = "\n".join(
                attachment.url
                for attachment in message.attachments[:5]
            )

            embed.add_field(
                name="Přílohy",
                value=attachments,
                inline=False,
            )

        await self.send_log(
            message.guild,
            "messages",
            embed,
        )

    @commands.Cog.listener()
    async def on_message_edit(
        self,
        before: discord.Message,
        after: discord.Message,
    ):
        if (
            before.guild is None
            or before.author.bot
            or before.content == after.content
        ):
            return

        embed = discord.Embed(
            title="✏️ Zpráva upravena",
            color=EMBED_COLOR,
        )

        embed.add_field(
            name="Autor",
            value=f"{before.author.mention}\n`{before.author.id}`",
            inline=True,
        )

        embed.add_field(
            name="Kanál",
            value=before.channel.mention,
            inline=True,
        )

        embed.add_field(
            name="Předtím",
            value=before.content[:1000] or "*Prázdná zpráva*",
            inline=False,
        )

        embed.add_field(
            name="Potom",
            value=after.content[:1000] or "*Prázdná zpráva*",
            inline=False,
        )

        embed.add_field(
            name="Odkaz",
            value=f"[Přejít na zprávu]({after.jump_url})",
            inline=False,
        )

        await self.send_log(
            before.guild,
            "messages",
            embed,
        )

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ):
        if before.channel == after.channel:
            return

        if before.channel is None and after.channel is not None:
            title = "🔊 Připojení do voice"
            description = (
                f"{member.mention} se připojil do {after.channel.mention}."
            )
            color = EMBED_COLOR

        elif before.channel is not None and after.channel is None:
            title = "🔇 Odpojení z voice"
            description = (
                f"{member.mention} odešel z {before.channel.mention}."
            )
            color = EMBED_COLOR

        else:
            title = "🔁 Přesun ve voice"
            description = (
                f"{member.mention} se přesunul z "
                f"{before.channel.mention} do {after.channel.mention}."
            )
            color = EMBED_COLOR

        embed = discord.Embed(
            title=title,
            description=description,
            color=color,
        )

        embed.add_field(
            name="Uživatel",
            value=f"`{member.id}`",
            inline=False,
        )

        await self.send_log(
            member.guild,
            "voice",
            embed,
        )

    @commands.Cog.listener()
    async def on_guild_channel_create(
        self,
        channel: discord.abc.GuildChannel,
    ):
        embed = discord.Embed(
            title="➕ Kanál vytvořen",
            color=EMBED_COLOR,
        )

        embed.add_field(
            name="Kanál",
            value=f"{channel.mention}\n`{channel.id}`",
            inline=False,
        )

        embed.add_field(
            name="Typ",
            value=str(channel.type),
            inline=True,
        )

        await self.send_log(
            channel.guild,
            "channels",
            embed,
        )

    @commands.Cog.listener()
    async def on_guild_channel_delete(
        self,
        channel: discord.abc.GuildChannel,
    ):
        embed = discord.Embed(
            title="➖ Kanál smazán",
            color=EMBED_COLOR,
        )

        embed.add_field(
            name="Název",
            value=channel.name,
            inline=True,
        )

        embed.add_field(
            name="ID",
            value=f"`{channel.id}`",
            inline=True,
        )

        embed.add_field(
            name="Typ",
            value=str(channel.type),
            inline=True,
        )

        await self.send_log(
            channel.guild,
            "channels",
            embed,
        )

    @commands.Cog.listener()
    async def on_member_ban(
        self,
        guild: discord.Guild,
        user: discord.User | discord.Member,
    ):
        embed = discord.Embed(
            title="🔨 Uživatel zabanován",
            color=EMBED_COLOR,
        )

        embed.set_thumbnail(url=user.display_avatar.url)

        embed.add_field(
            name="Uživatel",
            value=f"{user}\n`{user.id}`",
            inline=False,
        )

        await self.send_log(
            guild,
            "bans",
            embed,
        )

    @commands.Cog.listener()
    async def on_member_unban(
        self,
        guild: discord.Guild,
        user: discord.User,
    ):
        embed = discord.Embed(
            title="✅ Uživatel odbanován",
            color=EMBED_COLOR,
        )

        embed.set_thumbnail(url=user.display_avatar.url)

        embed.add_field(
            name="Uživatel",
            value=f"{user}\n`{user.id}`",
            inline=False,
        )

        await self.send_log(
            guild,
            "bans",
            embed,
        )

    async def cog_app_command_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ):
        original = getattr(error, "original", error)

        if isinstance(original, discord.NotFound):
            logger.warning(
                "Modlogs interakce %s vypršela nebo už není dostupná.",
                interaction.id,
            )
            return

        if isinstance(error, app_commands.MissingPermissions):
            message = "❌ Tento příkaz může použít pouze administrátor."
        else:
            logger.exception(
                "Chyba modlogs příkazu: %s",
                error,
            )
            message = "❌ Nastala chyba při zpracování modlogs příkazu."

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
            logger.warning(
                "Na modlogs interakci %s už nebylo možné odpovědět.",
                interaction.id,
            )

        except discord.HTTPException as response_error:
            logger.warning(
                "Discord odmítl odpověď na modlogs interakci %s: %s",
                interaction.id,
                response_error,
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(ModLogs(bot))
