from __future__ import annotations

from typing import Any

import discord
from discord import app_commands
from discord.ext import commands

from config import EMBED_COLOR, EMBED_FOOTER, VERSION
from utils.database import db
from utils.logger import logger


def _value(row: Any, key: str, default: Any = None) -> Any:
    if row is None:
        return default
    try:
        value = row[key]
    except (KeyError, IndexError, TypeError):
        return default
    return default if value is None else value


def _ignored_channels(raw_value: object) -> list[int]:
    result: list[int] = []
    for item in str(raw_value or "").split(","):
        try:
            result.append(int(item.strip()))
        except ValueError:
            continue
    return result


def _missing_channel_permissions(
    channel: discord.abc.GuildChannel,
    member: discord.Member,
    required: tuple[str, ...],
) -> list[str]:
    permissions = channel.permissions_for(member)
    return [name for name in required if not getattr(permissions, name, False)]


PERMISSION_LABELS = {
    "view_channel": "Zobrazit kanál",
    "send_messages": "Posílat zprávy",
    "embed_links": "Vkládat odkazy",
    "manage_roles": "Spravovat role",
    "manage_channels": "Spravovat kanály",
    "manage_messages": "Spravovat zprávy",
    "moderate_members": "Moderovat členy",
    "create_public_threads": "Vytvářet veřejná vlákna",
    "send_messages_in_threads": "Posílat zprávy ve vláknech",
}


def _permission_text(names: list[str]) -> str:
    return ", ".join(PERMISSION_LABELS.get(name, name) for name in names)


class Diagnostics(commands.GroupCog, name="diagnostika"):
    """Kontrola konfigurace a oprávnění jednotlivých modulů serveru."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="server",
        description="Zkontroluje nastavení a oprávnění bota na tomto serveru.",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def server(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "❌ Tento příkaz lze použít pouze na serveru.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        bot_member = guild.me
        if bot_member is None:
            await interaction.followup.send(
                "❌ Discord neposkytl členský záznam bota pro tento server.",
                ephemeral=True,
            )
            return

        sections: list[tuple[str, list[str]]] = []
        issue_count = 0
        warning_count = 0

        def add_section(title: str, lines: list[str]) -> None:
            sections.append((title, lines))

        core: list[str] = []
        try:
            db.stats()
        except Exception:
            logger.exception("Diagnostika: kontrola databáze selhala.")
            core.append("❌ **Databáze:** spojení selhalo")
            issue_count += 1
        else:
            core.append("✅ **Databáze:** dostupná")
        core.append(f"✅ **Discord:** připojeno, latence {round(self.bot.latency * 1000)} ms")
        core.append(f"ℹ️ **Verze:** {VERSION}")
        core.append(f"ℹ️ **Nejvyšší role bota:** {bot_member.top_role.mention}")
        add_section("Základ", core)

        try:
            autorole = db.get_autorole_settings(guild.id)
            welcome = db.get_welcome_settings(guild.id)
            antispam = db.get_antispam_settings(guild.id)
            pc_advice = db.get_pc_advice_settings(guild.id)
            youtube = db.get_guild_subscriptions(guild.id)
        except Exception:
            logger.exception("Diagnostika: načtení konfigurace serveru %s selhalo.", guild.id)
            await interaction.followup.send(
                "❌ Databáze odpověděla při základní kontrole, ale nepodařilo se "
                "načíst konfiguraci serveru. Zkontroluj log bota.",
                ephemeral=True,
            )
            return

        lines: list[str] = []
        if autorole is None or not bool(_value(autorole, "enabled", False)):
            lines.append("⚪ Modul je vypnutý nebo nenastavený.")
        else:
            role = guild.get_role(int(_value(autorole, "role_id", 0)))
            problems: list[str] = []
            if role is None:
                problems.append("uložená role neexistuje")
            elif role >= bot_member.top_role:
                problems.append("role bota není nad AutoRole")
            if not bot_member.guild_permissions.manage_roles:
                problems.append("chybí Spravovat role")
            if problems:
                lines.append("❌ " + "; ".join(problems))
                issue_count += 1
            else:
                lines.append(f"✅ Aktivní, role {role.mention}")
        add_section("AutoRole", lines)

        lines = []
        if welcome is None or not bool(_value(welcome, "enabled", False)):
            lines.append("⚪ Modul je vypnutý nebo nenastavený.")
        else:
            channel = guild.get_channel(int(_value(welcome, "channel_id", 0)))
            problems = []
            if not isinstance(channel, discord.TextChannel):
                problems.append("welcome kanál neexistuje")
            else:
                missing = _missing_channel_permissions(
                    channel, bot_member, ("view_channel", "send_messages", "embed_links")
                )
                if missing:
                    problems.append(f"v {channel.mention} chybí: {_permission_text(missing)}")
            role_id = int(_value(welcome, "role_id", 0) or 0)
            if role_id:
                role = guild.get_role(role_id)
                if role is None:
                    problems.append("welcome role neexistuje")
                elif role >= bot_member.top_role:
                    problems.append("role bota není nad welcome rolí")
                if not bot_member.guild_permissions.manage_roles:
                    problems.append("chybí Spravovat role")
            if problems:
                lines.append("❌ " + "; ".join(problems))
                issue_count += 1
            else:
                lines.append(f"✅ Aktivní v {channel.mention}")
        add_section("Welcome", lines)

        lines = []
        if antispam is None or not bool(_value(antispam, "enabled", False)):
            lines.append("⚪ Modul je vypnutý nebo nenastavený.")
        else:
            required = ("manage_messages", "moderate_members")
            missing = [
                name
                for name in required
                if not getattr(bot_member.guild_permissions, name, False)
            ]
            ignored = _ignored_channels(_value(antispam, "ignored_channel_ids", ""))
            missing_ignored = sum(
                guild.get_channel_or_thread(channel_id) is None for channel_id in ignored
            )
            if missing:
                lines.append(f"❌ Chybí: {_permission_text(missing)}")
                issue_count += 1
            else:
                lines.append(f"✅ Aktivní, ignorovaných kanálů: {len(ignored)}")
            if missing_ignored:
                lines.append(f"⚠️ {missing_ignored} ignorovaných kanálů už neexistuje")
                warning_count += 1
        add_section("AntiSpam", lines)

        lines = []
        if pc_advice is None or not bool(_value(pc_advice, "enabled", False)):
            lines.append("⚪ Modul je vypnutý nebo nenastavený.")
        else:
            problems = []
            panel = guild.get_channel(int(_value(pc_advice, "panel_channel_id", 0)))
            if not isinstance(panel, discord.TextChannel):
                problems.append("kanál panelu neexistuje")
            else:
                missing = _missing_channel_permissions(
                    panel, bot_member, ("view_channel", "send_messages", "embed_links")
                )
                if missing:
                    problems.append(f"v panelu chybí: {_permission_text(missing)}")

            advisor_role = guild.get_role(int(_value(pc_advice, "advisor_role_id", 0)))
            if advisor_role is None:
                problems.append("role poradců neexistuje")

            mode = str(_value(pc_advice, "mode", "private"))
            if mode in {"forum", "choice"}:
                forum_id = int(_value(pc_advice, "forum_channel_id", 0) or 0)
                forum = guild.get_channel(forum_id)
                if not isinstance(forum, discord.ForumChannel):
                    problems.append("poradenské fórum neexistuje")
                else:
                    missing = _missing_channel_permissions(
                        forum,
                        bot_member,
                        (
                            "view_channel",
                            "send_messages",
                            "create_public_threads",
                            "send_messages_in_threads",
                        ),
                    )
                    if missing:
                        problems.append(f"ve fóru chybí: {_permission_text(missing)}")
            if mode in {"private", "choice"}:
                category_id = int(_value(pc_advice, "category_id", 0) or 0)
                category = guild.get_channel(category_id)
                if not isinstance(category, discord.CategoryChannel):
                    problems.append("kategorie soukromé poradny neexistuje")
                elif not bot_member.guild_permissions.manage_channels:
                    problems.append("chybí Spravovat kanály")

            if problems:
                lines.append("❌ " + "; ".join(problems))
                issue_count += 1
            else:
                mode_label = {
                    "private": "soukromá",
                    "forum": "veřejné fórum",
                    "choice": "volba uživatele",
                }.get(mode, mode)
                lines.append(f"✅ Aktivní, režim: {mode_label}")
        add_section("PC poradna", lines)

        lines = []
        enabled_subscriptions = [row for row in youtube if bool(_value(row, "enabled", False))]
        invalid_channels = 0
        invalid_roles = 0
        permission_errors = 0
        for subscription in enabled_subscriptions:
            channel = guild.get_channel(int(_value(subscription, "discord_channel_id", 0)))
            if not isinstance(channel, discord.TextChannel):
                invalid_channels += 1
                continue
            if _missing_channel_permissions(
                channel, bot_member, ("view_channel", "send_messages", "embed_links")
            ):
                permission_errors += 1
            role_id = int(_value(subscription, "mention_role_id", 0) or 0)
            if role_id and guild.get_role(role_id) is None:
                invalid_roles += 1
        if not youtube:
            lines.append("⚪ Nejsou nastavené žádné odběry.")
        elif invalid_channels or permission_errors or invalid_roles:
            lines.append(
                "❌ Aktivních odběrů: "
                f"{len(enabled_subscriptions)}, chybné kanály: {invalid_channels}, "
                f"kanály bez oprávnění: {permission_errors}, chybné role: {invalid_roles}"
            )
            issue_count += 1
        else:
            lines.append(
                f"✅ Aktivních odběrů: {len(enabled_subscriptions)}, "
                f"pozastavených: {len(youtube) - len(enabled_subscriptions)}"
            )
        add_section("YouTube", lines)

        color = 0xED4245 if issue_count else (0xFEE75C if warning_count else 0x57F287)
        embed = discord.Embed(
            title="🩺 Diagnostika serveru",
            description=(
                f"Kontrola serveru **{guild.name}** dokončena. "
                f"Chyby: **{issue_count}**, upozornění: **{warning_count}**."
            ),
            color=color or EMBED_COLOR,
        )
        for title, section_lines in sections:
            embed.add_field(name=title, value="\n".join(section_lines)[:1024], inline=False)
        embed.set_footer(text=f"{EMBED_FOOTER} • Výsledek vidíš pouze ty")
        await interaction.followup.send(embed=embed, ephemeral=True)

    async def cog_app_command_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        if isinstance(error, app_commands.MissingPermissions):
            message = "❌ Tento příkaz může použít pouze administrátor."
        else:
            logger.exception("Diagnostika serveru selhala: %s", error)
            message = "❌ Diagnostika selhala. Podrobnosti jsou v logu bota."
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Diagnostics(bot))
