"""Panel s reakcemi pro dobrovolné serverové role."""

from __future__ import annotations

import asyncio

import discord
from discord import app_commands
from discord.ext import commands

from config import EMBED_COLOR, EMBED_FOOTER
from utils.database import db
from utils.logger import logger


FORBIDDEN_PERMISSIONS = (
    "administrator",
    "manage_guild",
    "manage_channels",
    "manage_roles",
    "manage_webhooks",
    "kick_members",
    "ban_members",
    "moderate_members",
)


class ReactionRoles(commands.GroupCog, name="reakcnirole"):
    """Dobrovolné role přidávané klasickou Discord reakcí."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @staticmethod
    def role_problem(guild: discord.Guild, role: discord.Role) -> str | None:
        me = guild.me
        if role.is_default() or role.managed:
            return "Tato role není vhodná pro reakční panel."
        if me is None or not me.guild_permissions.manage_roles:
            return "Bot potřebuje oprávnění **Spravovat role**."
        if role >= me.top_role:
            return "Role musí být v seznamu rolí pod nejvyšší rolí bota."
        if any(getattr(role.permissions, permission, False) for permission in FORBIDDEN_PERMISSIONS):
            return "Role má citlivé oprávnění a nelze ji rozdávat přes reakční panel."
        return None

    @staticmethod
    def _embed(settings: dict, guild: discord.Guild) -> discord.Embed:
        lines = []
        for entry in settings["entries"]:
            role = guild.get_role(int(entry["role_id"]))
            role_text = role.mention if role else f"nenalezená role (`{entry['role_id']}`)"
            lines.append(f"{entry['emoji']} — {role_text}")
        embed = discord.Embed(
            title=settings["title"],
            description=(settings["description"] + "\n\n" + "\n".join(lines))[:4096],
            color=EMBED_COLOR,
        )
        embed.set_footer(text=EMBED_FOOTER)
        return embed

    async def _get_panel_channel(
        self, guild: discord.Guild, channel_id: int
    ) -> discord.TextChannel | None:
        channel = guild.get_channel(channel_id)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(channel_id)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                return None
        return channel if isinstance(channel, discord.TextChannel) else None

    @app_commands.command(
        name="panel",
        description="Odešle nastavený panel reakcí do vybraného kanálu.",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def panel(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "❌ Tento příkaz lze použít pouze na serveru.", ephemeral=True
            )
            return
        await interaction.response.defer(ephemeral=True)
        settings = await asyncio.to_thread(db.get_reaction_role_settings, interaction.guild.id)
        if not settings["enabled"] or not settings["entries"]:
            await interaction.followup.send(
                "❌ Nejdřív nastav a ulož reakční role v dashboardu.", ephemeral=True
            )
            return
        channel_id = settings["channel_id"]
        if not channel_id.isdigit():
            await interaction.followup.send(
                "❌ V dashboardu chybí kanál pro reakční panel.", ephemeral=True
            )
            return
        channel = await self._get_panel_channel(interaction.guild, int(channel_id))
        me = interaction.guild.me
        permissions = channel.permissions_for(me) if channel and me else None
        if not channel or not permissions or not (
            permissions.view_channel and permissions.send_messages and permissions.add_reactions
        ):
            await interaction.followup.send(
                "❌ Bot v nastaveném kanálu potřebuje Zobrazit kanál, Posílat zprávy a Přidávat reakce.",
                ephemeral=True,
            )
            return

        for entry in settings["entries"]:
            role = interaction.guild.get_role(int(entry["role_id"]))
            if role is None:
                await interaction.followup.send(
                    f"❌ Nastavená role `{entry['role_id']}` už na serveru neexistuje.",
                    ephemeral=True,
                )
                return
            problem = self.role_problem(interaction.guild, role)
            if problem:
                await interaction.followup.send(
                    f"❌ {role.mention}: {problem}", ephemeral=True
                )
                return

        try:
            message = await channel.send(embed=self._embed(settings, interaction.guild))
            for entry in settings["entries"]:
                await message.add_reaction(entry["emoji"])
        except discord.HTTPException as error:
            if "message" in locals():
                try:
                    await message.delete()
                except discord.HTTPException:
                    pass
            logger.warning("Odeslání reakčního panelu na serveru %s selhalo: %s", interaction.guild.id, error)
            await interaction.followup.send(
                "❌ Panel se nepodařilo odeslat. Zkontroluj emoji a oprávnění bota v kanálu.",
                ephemeral=True,
            )
            return

        await asyncio.to_thread(
            db.set_reaction_role_message_id, interaction.guild.id, message.id
        )
        await interaction.followup.send(
            f"✅ Reakční panel byl odeslán do {channel.mention}. Starší panel už role měnit nebude.",
            ephemeral=True,
        )

    @app_commands.command(
        name="info",
        description="Zobrazí stav reakčních rolí na tomto serveru.",
    )
    async def info(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "❌ Tento příkaz lze použít pouze na serveru.", ephemeral=True
            )
            return
        settings = await asyncio.to_thread(db.get_reaction_role_settings, interaction.guild.id)
        if not settings["entries"]:
            await interaction.response.send_message(
                "📭 Reakční role zatím nejsou nastavené.", ephemeral=True
            )
            return
        status = "🟢 Aktivní" if settings["enabled"] and settings["message_id"] else "🟡 Čeká na odeslání panelu"
        embed = self._embed(settings, interaction.guild)
        embed.add_field(name="Stav", value=status, inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def _change_role(self, payload: discord.RawReactionActionEvent, *, add: bool) -> None:
        if payload.guild_id is None or self.bot.user is None or payload.user_id == self.bot.user.id:
            return
        emoji = str(payload.emoji)
        role_id = await asyncio.to_thread(
            db.get_reaction_role_mapping, payload.guild_id, payload.message_id, emoji
        )
        if role_id is None:
            return
        guild = self.bot.get_guild(payload.guild_id)
        if guild is None:
            return
        role = guild.get_role(role_id)
        if role is None:
            logger.warning("Reakční role %s nebyla nalezena na serveru %s.", role_id, guild.id)
            return
        problem = self.role_problem(guild, role)
        if problem:
            logger.warning("Reakční panel na serveru %s nemůže upravit roli %s: %s", guild.id, role.id, problem)
            return
        member = guild.get_member(payload.user_id)
        if member is None:
            try:
                member = await guild.fetch_member(payload.user_id)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                return
        try:
            if add and role not in member.roles:
                await member.add_roles(role, reason="Piticko Bot reakční role")
            elif not add and role in member.roles:
                await member.remove_roles(role, reason="Piticko Bot odebrání reakční role")
        except discord.Forbidden:
            logger.warning("Bot nemá oprávnění upravit reakční roli %s na serveru %s.", role.id, guild.id)
        except discord.HTTPException:
            logger.exception("Změna reakční role %s na serveru %s selhala.", role.id, guild.id)

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent) -> None:
        await self._change_role(payload, add=True)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent) -> None:
        await self._change_role(payload, add=False)

    async def cog_app_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        if isinstance(error, app_commands.MissingPermissions):
            message = "❌ Tento příkaz může použít pouze správce serveru."
        else:
            logger.exception("Chyba příkazu reakčních rolí: %s", error)
            message = "❌ Nastala chyba při práci s reakčními rolemi."
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(ReactionRoles(bot))
