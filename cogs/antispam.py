from __future__ import annotations

import asyncio
import time
from datetime import timedelta
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Deque, Optional

import discord
from discord import app_commands
from discord.ext import commands

from config import EMBED_COLOR, EMBED_FOOTER
from utils.database import db
from utils.logger import logger


@dataclass
class TrackedMessage:
    created_at: float
    message_id: int
    content: str


class AntiSpam(commands.GroupCog, name="antispam"):
    """Automatická ochrana serveru proti spamu."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

        self.message_history: dict[
            tuple[int, int],
            Deque[TrackedMessage],
        ] = defaultdict(lambda: deque(maxlen=30))

        self.processing_users: set[tuple[int, int]] = set()
        self.cooldowns: dict[tuple[int, int], float] = {}


    async def safe_defer(
        self,
        interaction: discord.Interaction,
    ) -> bool:
        try:
            await interaction.response.defer(ephemeral=True)
            return True
        except discord.NotFound:
            logger.warning(
                "AntiSpam interakce %s vypršela nebo už není dostupná.",
                interaction.id,
            )
            return False
        except discord.HTTPException as error:
            logger.warning(
                "Nepodařilo se potvrdit AntiSpam interakci %s: %s",
                interaction.id,
                error,
            )
            return False

    def get_settings(self, guild_id: int):
        return db.get_antispam_settings(guild_id)

    def save_settings(
        self,
        guild_id: int,
        max_messages: int,
        interval_seconds: int,
        duplicate_limit: int,
        mention_limit: int,
        timeout_minutes: int,
        delete_messages: bool,
    ) -> None:
        db.set_antispam_settings(
            guild_id,
            enabled=True,
            max_messages=max_messages,
            interval_seconds=interval_seconds,
            duplicate_limit=duplicate_limit,
            mention_limit=mention_limit,
            timeout_minutes=timeout_minutes,
            delete_messages=delete_messages,
        )

    def disable_settings(self, guild_id: int) -> None:
        db.set_antispam_enabled(guild_id, False)

    async def get_modlog_channel(
        self,
        guild: discord.Guild,
    ) -> Optional[discord.TextChannel]:
        try:
            with db.connect() as conn:
                settings = conn.execute("""
                    SELECT channel_id
                    FROM modlog_settings
                    WHERE guild_id = ?
                      AND enabled = 1
                """, (guild.id,)).fetchone()
        except Exception:
            logger.exception(
                "Nepodařilo se načíst modlog kanál pro AntiSpam."
            )
            return None

        if settings is None:
            return None

        channel = guild.get_channel(int(settings["channel_id"]))

        if isinstance(channel, discord.TextChannel):
            return channel

        return None

    async def send_log(
        self,
        message: discord.Message,
        reason: str,
        deleted_count: int,
        timeout_minutes: int,
    ) -> None:
        if message.guild is None:
            return

        channel = await self.get_modlog_channel(message.guild)

        if channel is None:
            return

        embed = discord.Embed(
            title="🚨 AntiSpam zásah",
            color=EMBED_COLOR,
            timestamp=discord.utils.utcnow(),
        )
        embed.add_field(
            name="Uživatel",
            value=f"{message.author.mention}\n`{message.author.id}`",
            inline=True,
        )
        embed.add_field(
            name="Kanál",
            value=message.channel.mention,
            inline=True,
        )
        embed.add_field(
            name="Důvod",
            value=reason,
            inline=False,
        )
        embed.add_field(
            name="Smazané zprávy",
            value=str(deleted_count),
            inline=True,
        )
        embed.add_field(
            name="Timeout",
            value=f"{timeout_minutes} minut",
            inline=True,
        )
        embed.set_footer(text=EMBED_FOOTER)

        try:
            await channel.send(embed=embed)
        except discord.HTTPException:
            logger.exception(
                "Nepodařilo se odeslat AntiSpam log."
            )

    def detect_violation(
        self,
        history: Deque[TrackedMessage],
        message: discord.Message,
        settings,
    ) -> Optional[str]:
        now = time.monotonic()
        interval = int(settings["interval_seconds"])

        recent = [
            tracked
            for tracked in history
            if now - tracked.created_at <= interval
        ]

        if len(recent) >= int(settings["max_messages"]):
            return (
                f"Příliš mnoho zpráv: **{len(recent)}** zpráv "
                f"během **{interval} sekund**."
            )

        normalized = " ".join(message.content.lower().split())

        if normalized:
            duplicates = sum(
                1
                for tracked in recent
                if tracked.content == normalized
            )

            if duplicates >= int(settings["duplicate_limit"]):
                return (
                    f"Opakovaná zpráva byla odeslána "
                    f"**{duplicates}×**."
                )

        unique_mentions = {
            user.id
            for user in message.mentions
            if user.id != message.author.id
        }

        if len(unique_mentions) >= int(settings["mention_limit"]):
            return (
                f"Hromadné označování: "
                f"**{len(unique_mentions)} uživatelů** v jedné zprávě."
            )

        return None

    async def remove_recent_messages(
        self,
        message: discord.Message,
        history: Deque[TrackedMessage],
        interval_seconds: int,
    ) -> int:
        if not isinstance(message.channel, discord.TextChannel):
            return 0

        now = time.monotonic()
        recent_ids = {
            tracked.message_id
            for tracked in history
            if now - tracked.created_at <= interval_seconds + 3
        }

        if not recent_ids:
            return 0

        try:
            deleted = await message.channel.purge(
                limit=min(len(recent_ids) + 10, 100),
                check=lambda item: (
                    item.author.id == message.author.id
                    and item.id in recent_ids
                ),
                reason="Piticko Bot AntiSpam",
            )
            return len(deleted)

        except discord.Forbidden:
            logger.warning(
                "Bot nemá oprávnění mazat spam v kanálu %s.",
                message.channel.id,
            )
        except discord.HTTPException:
            logger.exception(
                "Nepodařilo se odstranit spam v kanálu %s.",
                message.channel.id,
            )

        return 0

    async def punish(
        self,
        message: discord.Message,
        settings,
        reason: str,
        history: Deque[TrackedMessage],
    ) -> None:
        if (
            message.guild is None
            or not isinstance(message.author, discord.Member)
        ):
            return

        key = (message.guild.id, message.author.id)

        if key in self.processing_users:
            return

        cooldown_until = self.cooldowns.get(key, 0)

        if time.monotonic() < cooldown_until:
            return

        self.processing_users.add(key)

        try:
            deleted_count = 0

            if settings["delete_messages"]:
                deleted_count = await self.remove_recent_messages(
                    message,
                    history,
                    int(settings["interval_seconds"]),
                )

            timeout_minutes = int(settings["timeout_minutes"])

            try:
                await message.author.timeout(
                    timedelta(minutes=timeout_minutes),
                    reason=f"Piticko Bot AntiSpam: {reason}",
                )
            except discord.Forbidden:
                logger.warning(
                    "Bot nemá oprávnění udělit AntiSpam timeout uživateli %s.",
                    message.author.id,
                )
            except discord.HTTPException:
                logger.exception(
                    "Discord odmítl AntiSpam timeout uživatele %s.",
                    message.author.id,
                )

            warning_embed = discord.Embed(
                title="🚨 AntiSpam",
                description=(
                    f"{message.author.mention}, byl jsi dočasně umlčen.\n\n"
                    f"**Důvod:** {reason}\n"
                    f"**Timeout:** {timeout_minutes} minut"
                ),
                color=EMBED_COLOR,
            )
            warning_embed.set_footer(text=EMBED_FOOTER)

            try:
                await message.channel.send(
                    embed=warning_embed,
                    delete_after=12,
                )
            except discord.HTTPException:
                pass

            await self.send_log(
                message,
                reason,
                deleted_count,
                timeout_minutes,
            )

            try:
                with db.connect() as conn:
                    row_id = (
                        "BIGSERIAL PRIMARY KEY"
                        if db.using_postgres
                        else "INTEGER PRIMARY KEY AUTOINCREMENT"
                    )

                    conn.execute(f"""
                        CREATE TABLE IF NOT EXISTS moderation_actions (
                            id {row_id},
                            guild_id BIGINT NOT NULL,
                            user_id BIGINT NOT NULL,
                            moderator_id BIGINT NOT NULL,
                            action TEXT NOT NULL,
                            reason TEXT NOT NULL,
                            duration_minutes INTEGER,
                            created_at TEXT NOT NULL
                        )
                    """)

                    conn.execute("""
                        INSERT INTO moderation_actions (
                            guild_id,
                            user_id,
                            moderator_id,
                            action,
                            reason,
                            duration_minutes,
                            created_at
                        )
                        VALUES (?, ?, ?, 'antispam_timeout', ?, ?, ?)
                    """, (
                        message.guild.id,
                        message.author.id,
                        self.bot.user.id if self.bot.user else 0,
                        reason,
                        timeout_minutes,
                        db.now(),
                    ))
                    conn.commit()
            except Exception:
                logger.exception(
                    "Nepodařilo se uložit AntiSpam zásah do historie."
                )

            history.clear()
            self.cooldowns[key] = time.monotonic() + 30

            logger.info(
                "AntiSpam zasáhl proti uživateli %s na serveru %s: %s",
                message.author.id,
                message.guild.id,
                reason,
            )

        finally:
            self.processing_users.discard(key)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if (
            message.guild is None
            or message.author.bot
            or not isinstance(message.author, discord.Member)
        ):
            return

        if (
            message.author.guild_permissions.administrator
            or message.author.guild_permissions.manage_messages
        ):
            return

        try:
            settings = self.get_settings(message.guild.id)
        except Exception:
            logger.exception(
                "Nepodařilo se načíst AntiSpam nastavení."
            )
            return

        if settings is None or not settings["enabled"]:
            return

        key = (message.guild.id, message.author.id)
        history = self.message_history[key]
        now = time.monotonic()

        normalized = " ".join(message.content.lower().split())

        history.append(
            TrackedMessage(
                created_at=now,
                message_id=message.id,
                content=normalized,
            )
        )

        maximum_age = max(
            int(settings["interval_seconds"]) + 10,
            30,
        )

        while (
            history
            and now - history[0].created_at > maximum_age
        ):
            history.popleft()

        reason = self.detect_violation(
            history,
            message,
            settings,
        )

        if reason:
            await self.punish(
                message,
                settings,
                reason,
                history,
            )

    @app_commands.command(
        name="setup",
        description="Nastaví AntiSpam ochranu serveru.",
    )
    @app_commands.describe(
        max_messages="Kolik zpráv smí člen poslat během intervalu",
        interval_seconds="Délka sledovaného intervalu v sekundách",
        duplicate_limit="Kolikrát se smí opakovat stejná zpráva",
        mention_limit="Maximální počet označených lidí v jedné zprávě",
        timeout_minutes="Délka automatického timeoutu",
        delete_messages="Smazat při zásahu poslední spam zprávy",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def setup(
        self,
        interaction: discord.Interaction,
        max_messages: app_commands.Range[int, 3, 20] = 6,
        interval_seconds: app_commands.Range[int, 3, 60] = 8,
        duplicate_limit: app_commands.Range[int, 2, 10] = 3,
        mention_limit: app_commands.Range[int, 2, 20] = 5,
        timeout_minutes: app_commands.Range[int, 1, 1440] = 10,
        delete_messages: bool = True,
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

        missing = []

        if not bot_member.guild_permissions.moderate_members:
            missing.append("Moderovat členy")

        if delete_messages and not bot_member.guild_permissions.manage_messages:
            missing.append("Spravovat zprávy")

        if missing:
            await interaction.followup.send(
                "❌ Botovi chybí oprávnění: "
                + ", ".join(f"**{item}**" for item in missing),
                ephemeral=True,
            )
            return

        db.add_guild(
            interaction.guild.id,
            interaction.guild.name,
        )

        self.save_settings(
            interaction.guild.id,
            max_messages,
            interval_seconds,
            duplicate_limit,
            mention_limit,
            timeout_minutes,
            delete_messages,
        )

        embed = discord.Embed(
            title="✅ AntiSpam byl nastaven",
            description=(
                "Administrátoři a členové s oprávněním "
                "**Spravovat zprávy** jsou z kontroly vynecháni."
            ),
            color=EMBED_COLOR,
        )
        embed.add_field(
            name="Rychlý spam",
            value=(
                f"Max. **{max_messages} zpráv** "
                f"za **{interval_seconds} sekund**"
            ),
            inline=False,
        )
        embed.add_field(
            name="Opakované zprávy",
            value=f"Limit: **{duplicate_limit}×**",
            inline=True,
        )
        embed.add_field(
            name="Označování",
            value=f"Limit: **{mention_limit} lidí**",
            inline=True,
        )
        embed.add_field(
            name="Trest",
            value=f"Timeout na **{timeout_minutes} minut**",
            inline=False,
        )
        embed.add_field(
            name="Mazání spamu",
            value="✅ Zapnuto" if delete_messages else "❌ Vypnuto",
            inline=True,
        )
        embed.set_footer(text=EMBED_FOOTER)

        await interaction.followup.send(
            embed=embed,
            ephemeral=True,
        )

    @app_commands.command(
        name="info",
        description="Zobrazí aktuální AntiSpam nastavení.",
    )
    async def info(
        self,
        interaction: discord.Interaction,
    ):
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
                "📭 AntiSpam zatím není nastavený.",
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title="🛡️ AntiSpam nastavení",
            color=EMBED_COLOR,
        )
        embed.add_field(
            name="Stav",
            value="🟢 Zapnuto" if settings["enabled"] else "🔴 Vypnuto",
            inline=True,
        )
        embed.add_field(
            name="Rychlý spam",
            value=(
                f"{settings['max_messages']} zpráv / "
                f"{settings['interval_seconds']} s"
            ),
            inline=True,
        )
        embed.add_field(
            name="Opakování",
            value=f"{settings['duplicate_limit']}×",
            inline=True,
        )
        embed.add_field(
            name="Mention limit",
            value=str(settings["mention_limit"]),
            inline=True,
        )
        embed.add_field(
            name="Timeout",
            value=f"{settings['timeout_minutes']} minut",
            inline=True,
        )
        embed.add_field(
            name="Mazání zpráv",
            value="✅" if settings["delete_messages"] else "❌",
            inline=True,
        )
        embed.set_footer(text=EMBED_FOOTER)

        await interaction.followup.send(
            embed=embed,
            ephemeral=True,
        )

    @app_commands.command(
        name="disable",
        description="Vypne AntiSpam ochranu.",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def disable(
        self,
        interaction: discord.Interaction,
    ):
        if not await self.safe_defer(interaction):
            return

        if interaction.guild is None:
            await interaction.followup.send(
                "❌ Tento příkaz lze použít pouze na serveru.",
                ephemeral=True,
            )
            return

        self.disable_settings(interaction.guild.id)

        self.message_history = defaultdict(
            lambda: deque(maxlen=30)
        )

        await interaction.followup.send(
            "✅ AntiSpam ochrana byla vypnuta.",
            ephemeral=True,
        )

    @app_commands.command(
        name="test",
        description="Zobrazí pokyny pro bezpečné otestování AntiSpamu.",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def test(
        self,
        interaction: discord.Interaction,
    ):
        if not await self.safe_defer(interaction):
            return

        await interaction.followup.send(
            (
                "🧪 **Jak AntiSpam otestovat**\n\n"
                "Použij běžný testovací účet bez administrátorských "
                "oprávnění a rychle odešli několik zpráv.\n\n"
                "Administrátoři a členové s oprávněním "
                "**Spravovat zprávy** jsou úmyslně vynecháni."
            ),
            ephemeral=True,
        )

    async def cog_app_command_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ):
        original = getattr(error, "original", error)

        if isinstance(original, discord.NotFound):
            logger.warning(
                "AntiSpam interakce %s vypršela.",
                interaction.id,
            )
            return

        if isinstance(error, app_commands.MissingPermissions):
            message = "❌ Tento příkaz může použít pouze administrátor."
        else:
            logger.exception(
                "Chyba AntiSpam příkazu: %s",
                error,
            )
            message = "❌ Nastala chyba při zpracování AntiSpam příkazu."

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
        except discord.HTTPException:
            logger.warning(
                "Na AntiSpam interakci %s už nešlo odpovědět.",
                interaction.id,
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(AntiSpam(bot))
