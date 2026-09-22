from __future__ import annotations

from typing import Any

import discord
from discord import app_commands
from discord.ext import commands

from config import EMBED_COLOR, EMBED_FOOTER
from utils.database import db
from utils.logger import logger
from cogs.welcome import DEFAULT_WELCOME_MESSAGE


PERMISSION_LABELS = {
    "view_channel": "Zobrazit kanál",
    "send_messages": "Posílat zprávy",
    "embed_links": "Vkládat odkazy",
    "manage_roles": "Spravovat role",
    "manage_messages": "Spravovat zprávy",
    "moderate_members": "Moderovat členy",
}


def _value(row: Any, key: str, default: Any = None) -> Any:
    if row is None:
        return default
    try:
        value = row[key]
    except (KeyError, IndexError, TypeError):
        return default
    return default if value is None else value


def _missing_permissions(
    channel: discord.abc.GuildChannel,
    member: discord.Member,
    required: tuple[str, ...],
) -> list[str]:
    permissions = channel.permissions_for(member)
    return [name for name in required if not getattr(permissions, name, False)]


def _permission_text(names: list[str]) -> str:
    return ", ".join(PERMISSION_LABELS.get(name, name) for name in names)


class Onboarding(commands.GroupCog, name="nastaveni"):
    """Bezpečný rychlý start pro nový Discord server."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="start",
        description="Nastaví bezpečný základ bota pro nový server.",
    )
    @app_commands.describe(
        welcome_kanal="Kam bot pošle uvítání nového člena",
        log_kanal="Kam bot pošle moderační logy",
        nova_role="Volitelná role, kterou dostane každý nový člen",
        zapnout_antispam="Zapnout základní ochranu proti spamu",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def start(
        self,
        interaction: discord.Interaction,
        welcome_kanal: discord.TextChannel,
        log_kanal: discord.TextChannel,
        nova_role: discord.Role | None = None,
        zapnout_antispam: bool = True,
    ) -> None:
        """Nastaví jen moduly, které lze bezpečně připravit jedním krokem."""
        if interaction.guild is None:
            await interaction.response.send_message(
                "❌ Tento příkaz lze použít pouze na serveru.", ephemeral=True
            )
            return

        bot_member = interaction.guild.me
        if bot_member is None:
            await interaction.response.send_message(
                "❌ Discord neposkytl členský záznam bota pro tento server.",
                ephemeral=True,
            )
            return

        problems: list[str] = []
        for label, channel in (("Welcome", welcome_kanal), ("Mod log", log_kanal)):
            missing = _missing_permissions(
                channel,
                bot_member,
                ("view_channel", "send_messages", "embed_links"),
            )
            if missing:
                problems.append(
                    f"{label} v {channel.mention}: chybí {_permission_text(missing)}"
                )

        if nova_role is not None:
            if nova_role.is_default() or nova_role.managed:
                problems.append("vybraná role není běžná přiřaditelná role")
            elif nova_role >= bot_member.top_role:
                problems.append("role bota musí být v seznamu rolí nad novou rolí")
            elif not bot_member.guild_permissions.manage_roles:
                problems.append("botovi chybí oprávnění Spravovat role")

        if problems:
            embed = discord.Embed(
                title="❌ Rychlé nastavení nebylo uloženo",
                description=(
                    "Neuložil jsem žádné změny, protože by část nastavení nefungovala.\n\n"
                    + "\n".join(f"• {problem}" for problem in problems)
                ),
                color=0xED4245,
            )
            embed.add_field(
                name="Jak to opravit",
                value=(
                    "Uprav oprávnění bota v uvedených kanálech. Pokud nastavuješ "
                    "roli, přetáhni roli bota v nastavení Serveru výš než tuto roli."
                ),
                inline=False,
            )
            embed.set_footer(text=f"{EMBED_FOOTER} • Výsledek vidíš pouze ty")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild

        try:
            db.add_guild(guild.id, guild.name)

            existing_welcome = db.get_welcome_settings(guild.id)
            db.set_welcome_settings(
                guild_id=guild.id,
                channel_id=welcome_kanal.id,
                role_id=(
                    nova_role.id
                    if nova_role is not None
                    else _value(existing_welcome, "role_id", None)
                ),
                message=str(_value(existing_welcome, "message", DEFAULT_WELCOME_MESSAGE)),
            )

            existing_modlog = db.get_modlog_settings(guild.id)
            db.set_modlog_settings(
                guild.id,
                log_kanal.id,
                enabled=True,
                log_members=bool(_value(existing_modlog, "log_members", True)),
                log_messages=bool(_value(existing_modlog, "log_messages", True)),
                log_voice=bool(_value(existing_modlog, "log_voice", True)),
                log_channels=bool(_value(existing_modlog, "log_channels", True)),
                log_bans=bool(_value(existing_modlog, "log_bans", True)),
            )

            antispam_enabled = False
            antispam_reason = "Vypnutý na přání správce."
            if zapnout_antispam:
                missing_antispam = [
                    name
                    for name in ("manage_messages", "moderate_members")
                    if not getattr(bot_member.guild_permissions, name, False)
                ]
                if missing_antispam:
                    antispam_reason = (
                        "Nezapnutý — botovi chybí "
                        f"{_permission_text(missing_antispam)}."
                    )
                else:
                    if db.get_antispam_settings(guild.id) is None:
                        db.set_antispam_settings(guild.id, enabled=True)
                    else:
                        db.set_antispam_enabled(guild.id, True)
                    antispam_enabled = True
                    antispam_reason = "Zapnutý se základními bezpečnými limity."
        except Exception:
            logger.exception("Rychlé nastavení serveru %s selhalo.", guild.id)
            await interaction.followup.send(
                "❌ Nastavení se nepodařilo uložit. Zkontroluj log bota.",
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title="✅ Základ bota je nastavený",
            description="Nastavil jsem jen bezpečný základ. Ostatní moduly zůstaly beze změny.",
            color=0x57F287,
        )
        embed.add_field(
            name="👋 Welcome",
            value=(
                f"Kanál: {welcome_kanal.mention}\n"
                f"Role: {nova_role.mention if nova_role else 'žádná'}"
            ),
            inline=False,
        )
        embed.add_field(
            name="🧾 Mod log",
            value=f"Kanál: {log_kanal.mention}",
            inline=False,
        )
        embed.add_field(
            name="🛡️ Anti-spam",
            value=("✅ " if antispam_enabled else "⚪ ") + antispam_reason,
            inline=False,
        )
        embed.add_field(
            name="Další doporučené kroky",
            value=(
                "1. `/welcome test` — ověří welcome zprávu.\n"
                "2. `/ticket setup` a potom `/ticket panel` — pokud chceš tickety.\n"
                "3. `/diagnostika server` — celková kontrola oprávnění a konfigurace.\n"
                "4. Další moduly nastav v dashboardu podle toho, co server opravdu potřebuje."
            ),
            inline=False,
        )
        embed.set_footer(text=f"{EMBED_FOOTER} • Výsledek vidíš pouze ty")
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(
        name="kontrola",
        description="Ukáže krátký seznam, co ještě nový server potřebuje nastavit.",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def check(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "❌ Tento příkaz lze použít pouze na serveru.", ephemeral=True
            )
            return

        guild_id = interaction.guild.id
        try:
            welcome = db.get_welcome_settings(guild_id)
            modlog = db.get_modlog_settings(guild_id)
            antispam = db.get_antispam_settings(guild_id)
            tickets = db.get_ticket_settings(guild_id)
        except Exception:
            logger.exception("Kontrola prvotního nastavení serveru %s selhala.", guild_id)
            await interaction.response.send_message(
                "❌ Kontrola selhala. Zkontroluj log bota.", ephemeral=True
            )
            return

        def state(row: Any) -> str:
            return "✅ Nastaveno" if row is not None and bool(_value(row, "enabled", False)) else "⚪ Nenastaveno"

        embed = discord.Embed(
            title="📋 Kontrola prvotního nastavení",
            description="Toto není chyba — jen přehled základních modulů pro nový server.",
            color=EMBED_COLOR,
        )
        embed.add_field(name="Welcome", value=state(welcome), inline=True)
        embed.add_field(name="Mod log", value=state(modlog), inline=True)
        embed.add_field(name="Anti-spam", value=state(antispam), inline=True)
        embed.add_field(name="Tickety", value=state(tickets), inline=True)
        embed.add_field(
            name="Co dál",
            value=(
                "Základ nastavíš přes `/nastaveni start`. Pro detailní kontrolu "
                "všech modulů použij `/diagnostika server`."
            ),
            inline=False,
        )
        embed.set_footer(text=f"{EMBED_FOOTER} • Výsledek vidíš pouze ty")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def cog_app_command_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        if isinstance(error, app_commands.MissingPermissions):
            message = "❌ Tento příkaz může použít pouze administrátor."
        else:
            logger.exception("Nastavení serveru selhalo: %s", error)
            message = "❌ Nastavení selhalo. Podrobnosti jsou v logu bota."
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Onboarding(bot))
