from __future__ import annotations

from datetime import timedelta
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from config import EMBED_COLOR, EMBED_FOOTER
from utils.database import db
from utils.logger import logger


MAX_REASON_LENGTH = 900


def clean_reason(reason: Optional[str]) -> str:
    value = (reason or "Důvod nebyl uveden.").strip()
    return value[:MAX_REASON_LENGTH]


def can_moderate(
    interaction: discord.Interaction,
    member: discord.Member,
) -> tuple[bool, str]:
    guild = interaction.guild

    if guild is None or not isinstance(interaction.user, discord.Member):
        return False, "❌ Tento příkaz lze použít pouze na serveru."

    if member.id == interaction.user.id:
        return False, "❌ Nemůžeš moderovat sám sebe."

    if member.id == guild.owner_id:
        return False, "❌ Majitele serveru nelze tímto příkazem moderovat."

    if interaction.user.id != guild.owner_id and member.top_role >= interaction.user.top_role:
        return False, "❌ Tento člen má stejnou nebo vyšší roli než ty."

    bot_member = guild.me

    if bot_member is None:
        return False, "❌ Nepodařilo se načíst účet bota."

    if member.top_role >= bot_member.top_role:
        return False, "❌ Role bota musí být výše než nejvyšší role tohoto člena."

    return True, ""


class Moderation(commands.GroupCog, name="moderation"):
    """Pokročilá moderace, varování, poznámky a historie zásahů."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def safe_defer(
        self,
        interaction: discord.Interaction,
        *,
        ephemeral: bool = True,
    ) -> bool:
        try:
            await interaction.response.defer(ephemeral=ephemeral)
            return True
        except discord.NotFound:
            logger.warning(
                "Moderation interakce %s vypršela nebo už není dostupná.",
                interaction.id,
            )
            return False
        except discord.HTTPException as error:
            logger.warning(
                "Nepodařilo se potvrdit moderation interakci %s: %s",
                interaction.id,
                error,
            )
            return False

    def _insert_returning_id(
        self,
        query: str,
        params: tuple,
    ) -> int:
        with db.connect() as conn:
            if db.using_postgres:
                row = conn.execute(
                    f"{query} RETURNING id",
                    params,
                ).fetchone()
                conn.commit()
                return int(row["id"])

            cursor = conn.execute(query, params)
            conn.commit()
            return int(cursor.lastrowid)

    def add_warning(
        self,
        guild_id: int,
        user_id: int,
        moderator_id: int,
        reason: str,
    ) -> int:
        return self._insert_returning_id(
            """
            INSERT INTO moderation_warnings
            (guild_id, user_id, moderator_id, reason, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                guild_id,
                user_id,
                moderator_id,
                reason,
                db.now(),
            ),
        )

    def add_action(
        self,
        guild_id: int,
        user_id: int,
        moderator_id: int,
        action: str,
        reason: str,
        duration_minutes: Optional[int] = None,
    ) -> int:
        return self._insert_returning_id(
            """
            INSERT INTO moderation_actions
            (
                guild_id,
                user_id,
                moderator_id,
                action,
                reason,
                duration_minutes,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                guild_id,
                user_id,
                moderator_id,
                action,
                reason,
                duration_minutes,
                db.now(),
            ),
        )

    def add_note(
        self,
        guild_id: int,
        user_id: int,
        moderator_id: int,
        note: str,
    ) -> int:
        return self._insert_returning_id(
            """
            INSERT INTO moderation_notes
            (guild_id, user_id, moderator_id, note, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                guild_id,
                user_id,
                moderator_id,
                note,
                db.now(),
            ),
        )

    def get_warnings(self, guild_id: int, user_id: int):
        with db.connect() as conn:
            return conn.execute("""
                SELECT *
                FROM moderation_warnings
                WHERE guild_id = ?
                  AND user_id = ?
                ORDER BY id DESC
                LIMIT 20
            """, (guild_id, user_id)).fetchall()

    def count_warnings(self, guild_id: int, user_id: int) -> int:
        with db.connect() as conn:
            row = conn.execute("""
                SELECT COUNT(*) AS c
                FROM moderation_warnings
                WHERE guild_id = ?
                  AND user_id = ?
            """, (guild_id, user_id)).fetchone()
            return int(row["c"])

    def clear_warnings(self, guild_id: int, user_id: int) -> int:
        with db.connect() as conn:
            cursor = conn.execute("""
                DELETE FROM moderation_warnings
                WHERE guild_id = ?
                  AND user_id = ?
            """, (guild_id, user_id))
            conn.commit()
            return cursor.rowcount

    def get_history(self, guild_id: int, user_id: int):
        with db.connect() as conn:
            return conn.execute("""
                SELECT *
                FROM moderation_actions
                WHERE guild_id = ?
                  AND user_id = ?
                ORDER BY id DESC
                LIMIT 20
            """, (guild_id, user_id)).fetchall()

    def get_notes(self, guild_id: int, user_id: int):
        with db.connect() as conn:
            return conn.execute("""
                SELECT *
                FROM moderation_notes
                WHERE guild_id = ?
                  AND user_id = ?
                ORDER BY id DESC
                LIMIT 20
            """, (guild_id, user_id)).fetchall()

    def get_auto_punishments(self, guild_id: int) -> bool:
        with db.connect() as conn:
            row = conn.execute("""
                SELECT auto_punishments
                FROM moderation_settings
                WHERE guild_id = ?
            """, (guild_id,)).fetchone()

        return bool(row["auto_punishments"]) if row else False

    def set_auto_punishments(self, guild_id: int, enabled: bool) -> None:
        with db.connect() as conn:
            if db.using_postgres:
                conn.execute("""
                    INSERT INTO moderation_settings
                    (guild_id, auto_punishments, updated_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT (guild_id)
                    DO UPDATE SET
                        auto_punishments = EXCLUDED.auto_punishments,
                        updated_at = EXCLUDED.updated_at
                """, (
                    guild_id,
                    1 if enabled else 0,
                    db.now(),
                ))
            else:
                conn.execute("""
                    INSERT OR REPLACE INTO moderation_settings
                    (guild_id, auto_punishments, updated_at)
                    VALUES (?, ?, ?)
                """, (
                    guild_id,
                    1 if enabled else 0,
                    db.now(),
                ))

            conn.commit()

    async def send_dm(
        self,
        member: discord.Member,
        *,
        title: str,
        description: str,
    ) -> None:
        embed = discord.Embed(
            title=title,
            description=description,
            color=EMBED_COLOR,
        )
        embed.set_footer(text=EMBED_FOOTER)

        try:
            await member.send(embed=embed)
        except (discord.Forbidden, discord.HTTPException):
            pass

    async def send_modlog(
        self,
        guild: discord.Guild,
        *,
        title: str,
        member: discord.abc.User,
        moderator: discord.abc.User,
        reason: str,
        color: discord.Color,
        extra: Optional[str] = None,
    ) -> None:
        try:
            with db.connect() as conn:
                settings = conn.execute("""
                    SELECT *
                    FROM modlog_settings
                    WHERE guild_id = ?
                      AND enabled = 1
                """, (guild.id,)).fetchone()
        except Exception:
            logger.exception("Nepodařilo se načíst modlog kanál.")
            return

        if settings is None:
            return

        channel = guild.get_channel(int(settings["channel_id"]))

        if not isinstance(channel, discord.TextChannel):
            return

        embed = discord.Embed(
            title=title,
            color=color,
            timestamp=discord.utils.utcnow(),
        )
        embed.add_field(
            name="Uživatel",
            value=f"{member}\n`{member.id}`",
            inline=True,
        )
        embed.add_field(
            name="Moderátor",
            value=f"{moderator}\n`{moderator.id}`",
            inline=True,
        )
        embed.add_field(
            name="Důvod",
            value=reason,
            inline=False,
        )

        if extra:
            embed.add_field(
                name="Podrobnosti",
                value=extra,
                inline=False,
            )

        embed.set_footer(text=EMBED_FOOTER)

        try:
            await channel.send(embed=embed)
        except discord.HTTPException:
            logger.exception("Nepodařilo se odeslat moderation log.")

    async def apply_auto_punishment(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        warning_count: int,
    ) -> Optional[str]:
        if not self.get_auto_punishments(interaction.guild.id):
            return None

        reason = f"Automatický trest za {warning_count} varování."

        try:
            if warning_count == 3:
                await member.timeout(
                    timedelta(hours=1),
                    reason=reason,
                )
                self.add_action(
                    interaction.guild.id,
                    member.id,
                    self.bot.user.id,
                    "auto_timeout",
                    reason,
                    60,
                )
                return "⏳ Automaticky byl udělen timeout na 1 hodinu."

            if warning_count == 5:
                await member.kick(reason=reason)
                self.add_action(
                    interaction.guild.id,
                    member.id,
                    self.bot.user.id,
                    "auto_kick",
                    reason,
                )
                return "👢 Uživatel byl automaticky vyhozen."

            if warning_count >= 7:
                await interaction.guild.ban(
                    member,
                    reason=reason,
                    delete_message_seconds=0,
                )
                self.add_action(
                    interaction.guild.id,
                    member.id,
                    self.bot.user.id,
                    "auto_ban",
                    reason,
                )
                return "🔨 Uživatel byl automaticky zabanován."

        except discord.Forbidden:
            logger.warning(
                "Bot nemá oprávnění použít automatický trest na uživatele %s.",
                member.id,
            )
            return "⚠️ Automatický trest nešel použít kvůli oprávněním."

        except discord.HTTPException:
            logger.exception(
                "Discord odmítl automatický trest pro uživatele %s.",
                member.id,
            )
            return "⚠️ Discord odmítl automatický trest."

        return None

    @app_commands.command(
        name="autosystem",
        description="Zapne nebo vypne automatické tresty podle počtu warnů.",
    )
    @app_commands.describe(enabled="Zapnout nebo vypnout automatické tresty")
    @app_commands.checks.has_permissions(administrator=True)
    async def autosystem(
        self,
        interaction: discord.Interaction,
        enabled: bool,
    ):
        if not await self.safe_defer(interaction):
            return

        self.set_auto_punishments(
            interaction.guild.id,
            enabled,
        )

        status = "zapnuty" if enabled else "vypnuty"

        await interaction.followup.send(
            (
                f"✅ Automatické tresty byly **{status}**.\n\n"
                "3 warny → timeout 1 hodina\n"
                "5 warnů → kick\n"
                "7 warnů → ban"
            ),
            ephemeral=True,
        )

    @app_commands.command(
        name="warn",
        description="Udělí členovi varování a uloží ho do historie.",
    )
    @app_commands.describe(
        member="Člen, kterého chceš varovat",
        reason="Důvod varování",
    )
    @app_commands.checks.has_permissions(moderate_members=True)
    async def warn(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        reason: Optional[str] = None,
    ):
        if not await self.safe_defer(interaction):
            return

        allowed, message = can_moderate(interaction, member)

        if not allowed:
            await interaction.followup.send(message, ephemeral=True)
            return

        final_reason = clean_reason(reason)

        try:
            warning_id = self.add_warning(
                interaction.guild.id,
                member.id,
                interaction.user.id,
                final_reason,
            )
            self.add_action(
                interaction.guild.id,
                member.id,
                interaction.user.id,
                "warn",
                final_reason,
            )
            count = self.count_warnings(
                interaction.guild.id,
                member.id,
            )
        except Exception:
            logger.exception("Nepodařilo se uložit varování.")
            await interaction.followup.send(
                "❌ Varování se nepodařilo uložit do databáze.",
                ephemeral=True,
            )
            return

        await self.send_dm(
            member,
            title=f"⚠️ Varování na serveru {interaction.guild.name}",
            description=(
                f"**Důvod:** {final_reason}\n"
                f"**Moderátor:** {interaction.user}\n"
                f"**Celkem varování:** {count}"
            ),
        )

        automatic_result = await self.apply_auto_punishment(
            interaction,
            member,
            count,
        )

        await self.send_modlog(
            interaction.guild,
            title="⚠️ Varování uděleno",
            member=member,
            moderator=interaction.user,
            reason=final_reason,
            color=EMBED_COLOR,
            extra=f"ID varování: {warning_id}\nCelkem varování: {count}",
        )

        embed = discord.Embed(
            title="⚠️ Varování uděleno",
            color=EMBED_COLOR,
        )
        embed.add_field(name="Člen", value=member.mention, inline=True)
        embed.add_field(name="Moderátor", value=interaction.user.mention, inline=True)
        embed.add_field(name="ID varování", value=f"`{warning_id}`", inline=True)
        embed.add_field(name="Celkem varování", value=str(count), inline=True)
        embed.add_field(name="Důvod", value=final_reason, inline=False)

        if automatic_result:
            embed.add_field(
                name="Automatický systém",
                value=automatic_result,
                inline=False,
            )

        embed.set_footer(text=EMBED_FOOTER)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(
        name="warnings",
        description="Zobrazí poslední varování člena.",
    )
    @app_commands.describe(member="Člen, jehož varování chceš zobrazit")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def warnings(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
    ):
        if not await self.safe_defer(interaction):
            return

        rows = self.get_warnings(
            interaction.guild.id,
            member.id,
        )

        if not rows:
            await interaction.followup.send(
                f"✅ {member.mention} nemá žádná uložená varování.",
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title=f"⚠️ Varování — {member}",
            color=EMBED_COLOR,
        )
        embed.set_thumbnail(url=member.display_avatar.url)

        for row in rows[:10]:
            reason = row["reason"][:250]
            embed.add_field(
                name=f"Varování #{row['id']}",
                value=(
                    f"**Moderátor:** <@{row['moderator_id']}>\n"
                    f"**Důvod:** {reason}\n"
                    f"**Čas:** `{row['created_at']}`"
                ),
                inline=False,
            )

        embed.set_footer(text=EMBED_FOOTER)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(
        name="clearwarns",
        description="Smaže všechna uložená varování člena.",
    )
    @app_commands.describe(member="Člen, kterému chceš vymazat varování")
    @app_commands.checks.has_permissions(administrator=True)
    async def clearwarns(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
    ):
        if not await self.safe_defer(interaction):
            return

        removed = self.clear_warnings(
            interaction.guild.id,
            member.id,
        )

        self.add_action(
            interaction.guild.id,
            member.id,
            interaction.user.id,
            "clear_warnings",
            f"Odstraněno {removed} varování.",
        )

        await interaction.followup.send(
            f"✅ U člena {member.mention} bylo odstraněno **{removed}** varování.",
            ephemeral=True,
        )

    @app_commands.command(
        name="note",
        description="Přidá neveřejnou moderátorskou poznámku k členovi.",
    )
    @app_commands.describe(
        member="Člen, ke kterému chceš přidat poznámku",
        text="Text poznámky",
    )
    @app_commands.checks.has_permissions(moderate_members=True)
    async def note(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        text: str,
    ):
        if not await self.safe_defer(interaction):
            return

        note_id = self.add_note(
            interaction.guild.id,
            member.id,
            interaction.user.id,
            clean_reason(text),
        )

        await interaction.followup.send(
            f"✅ Poznámka `#{note_id}` byla přidána k {member.mention}.",
            ephemeral=True,
        )

    @app_commands.command(
        name="notes",
        description="Zobrazí neveřejné moderátorské poznámky člena.",
    )
    @app_commands.describe(member="Člen, jehož poznámky chceš zobrazit")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def notes(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
    ):
        if not await self.safe_defer(interaction):
            return

        rows = self.get_notes(
            interaction.guild.id,
            member.id,
        )

        if not rows:
            await interaction.followup.send(
                f"📭 {member.mention} nemá žádné moderátorské poznámky.",
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title=f"📝 Moderátorské poznámky — {member}",
            color=EMBED_COLOR,
        )

        for row in rows[:10]:
            embed.add_field(
                name=f"Poznámka #{row['id']}",
                value=(
                    f"**Moderátor:** <@{row['moderator_id']}>\n"
                    f"**Text:** {row['note'][:350]}\n"
                    f"**Čas:** `{row['created_at']}`"
                ),
                inline=False,
            )

        embed.set_footer(text=EMBED_FOOTER)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(
        name="history",
        description="Zobrazí historii moderačních zásahů člena.",
    )
    @app_commands.describe(member="Člen, jehož historii chceš zobrazit")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def history(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
    ):
        if not await self.safe_defer(interaction):
            return

        rows = self.get_history(
            interaction.guild.id,
            member.id,
        )

        if not rows:
            await interaction.followup.send(
                f"✅ {member.mention} nemá uloženou historii zásahů.",
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title=f"📋 Historie moderace — {member}",
            color=EMBED_COLOR,
        )

        for row in rows[:10]:
            duration = (
                f"\n**Délka:** {row['duration_minutes']} minut"
                if row["duration_minutes"]
                else ""
            )

            embed.add_field(
                name=f"{row['action']} #{row['id']}",
                value=(
                    f"**Moderátor:** <@{row['moderator_id']}>\n"
                    f"**Důvod:** {row['reason'][:300]}"
                    f"{duration}\n"
                    f"**Čas:** `{row['created_at']}`"
                ),
                inline=False,
            )

        embed.set_footer(text=EMBED_FOOTER)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(
        name="timeout",
        description="Dočasně umlčí člena.",
    )
    @app_commands.describe(
        member="Člen, kterému chceš udělit timeout",
        minutes="Délka timeoutu v minutách",
        reason="Důvod timeoutu",
    )
    @app_commands.checks.has_permissions(moderate_members=True)
    async def timeout(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        minutes: app_commands.Range[int, 1, 40320],
        reason: Optional[str] = None,
    ):
        if not await self.safe_defer(interaction):
            return

        allowed, message = can_moderate(interaction, member)

        if not allowed:
            await interaction.followup.send(message, ephemeral=True)
            return

        final_reason = clean_reason(reason)

        try:
            await member.timeout(
                timedelta(minutes=minutes),
                reason=f"{interaction.user}: {final_reason}",
            )
        except discord.Forbidden:
            await interaction.followup.send(
                "❌ Bot nemá oprávnění tomuto členovi udělit timeout.",
                ephemeral=True,
            )
            return

        self.add_action(
            interaction.guild.id,
            member.id,
            interaction.user.id,
            "timeout",
            final_reason,
            minutes,
        )

        await self.send_modlog(
            interaction.guild,
            title="⏳ Timeout udělen",
            member=member,
            moderator=interaction.user,
            reason=final_reason,
            color=EMBED_COLOR,
            extra=f"Délka: {minutes} minut",
        )

        await interaction.followup.send(
            f"✅ {member.mention} dostal timeout na **{minutes} minut**.",
            ephemeral=True,
        )

    @app_commands.command(
        name="untimeout",
        description="Zruší členovi timeout.",
    )
    @app_commands.describe(member="Člen, kterému chceš zrušit timeout")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def untimeout(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
    ):
        if not await self.safe_defer(interaction):
            return

        allowed, message = can_moderate(interaction, member)

        if not allowed:
            await interaction.followup.send(message, ephemeral=True)
            return

        try:
            await member.timeout(None, reason=f"Zrušil {interaction.user}")
        except discord.Forbidden:
            await interaction.followup.send(
                "❌ Bot nemá oprávnění timeout zrušit.",
                ephemeral=True,
            )
            return

        self.add_action(
            interaction.guild.id,
            member.id,
            interaction.user.id,
            "untimeout",
            "Timeout byl zrušen.",
        )

        await interaction.followup.send(
            f"✅ Timeout člena {member.mention} byl zrušen.",
            ephemeral=True,
        )

    @app_commands.command(
        name="kick",
        description="Vyhodí člena ze serveru.",
    )
    @app_commands.describe(
        member="Člen, kterého chceš vyhodit",
        reason="Důvod vyhození",
    )
    @app_commands.checks.has_permissions(kick_members=True)
    async def kick(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        reason: Optional[str] = None,
    ):
        if not await self.safe_defer(interaction):
            return

        allowed, message = can_moderate(interaction, member)

        if not allowed:
            await interaction.followup.send(message, ephemeral=True)
            return

        final_reason = clean_reason(reason)

        try:
            await member.kick(reason=f"{interaction.user}: {final_reason}")
        except discord.Forbidden:
            await interaction.followup.send(
                "❌ Bot nemá oprávnění tohoto člena vyhodit.",
                ephemeral=True,
            )
            return

        self.add_action(
            interaction.guild.id,
            member.id,
            interaction.user.id,
            "kick",
            final_reason,
        )

        await self.send_modlog(
            interaction.guild,
            title="👢 Člen vyhozen",
            member=member,
            moderator=interaction.user,
            reason=final_reason,
            color=EMBED_COLOR,
        )

        await interaction.followup.send(
            f"✅ **{member}** byl vyhozen.",
            ephemeral=True,
        )

    @app_commands.command(
        name="ban",
        description="Zabanuje člena na serveru.",
    )
    @app_commands.describe(
        member="Člen, kterého chceš zabanovat",
        reason="Důvod banu",
        delete_days="Kolik dní zpráv smazat (0–7)",
    )
    @app_commands.checks.has_permissions(ban_members=True)
    async def ban(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        reason: Optional[str] = None,
        delete_days: app_commands.Range[int, 0, 7] = 0,
    ):
        if not await self.safe_defer(interaction):
            return

        allowed, message = can_moderate(interaction, member)

        if not allowed:
            await interaction.followup.send(message, ephemeral=True)
            return

        final_reason = clean_reason(reason)

        try:
            await interaction.guild.ban(
                member,
                reason=f"{interaction.user}: {final_reason}",
                delete_message_seconds=delete_days * 86400,
            )
        except discord.Forbidden:
            await interaction.followup.send(
                "❌ Bot nemá oprávnění tohoto člena zabanovat.",
                ephemeral=True,
            )
            return

        self.add_action(
            interaction.guild.id,
            member.id,
            interaction.user.id,
            "ban",
            final_reason,
        )

        await self.send_modlog(
            interaction.guild,
            title="🔨 Člen zabanován",
            member=member,
            moderator=interaction.user,
            reason=final_reason,
            color=EMBED_COLOR,
        )

        await interaction.followup.send(
            f"✅ **{member}** byl zabanován.",
            ephemeral=True,
        )

    @app_commands.command(
        name="clear",
        description="Smaže zprávy v aktuálním kanálu.",
    )
    @app_commands.describe(
        amount="Počet zpráv (1–100)",
        member="Volitelně jen zprávy konkrétního člena",
    )
    @app_commands.checks.has_permissions(manage_messages=True)
    async def clear(
        self,
        interaction: discord.Interaction,
        amount: app_commands.Range[int, 1, 100],
        member: Optional[discord.Member] = None,
    ):
        if not await self.safe_defer(interaction):
            return

        if not isinstance(interaction.channel, discord.TextChannel):
            await interaction.followup.send(
                "❌ Příkaz lze použít pouze v textovém kanálu.",
                ephemeral=True,
            )
            return

        try:
            deleted = await interaction.channel.purge(
                limit=amount,
                check=(
                    (lambda message: message.author.id == member.id)
                    if member
                    else None
                ),
                reason=f"Moderation clear by {interaction.user}",
            )
        except discord.Forbidden:
            await interaction.followup.send(
                "❌ Bot nemá oprávnění spravovat zprávy.",
                ephemeral=True,
            )
            return

        self.add_action(
            interaction.guild.id,
            member.id if member else 0,
            interaction.user.id,
            "clear",
            f"Smazáno {len(deleted)} zpráv v kanálu {interaction.channel.name}.",
        )

        await interaction.followup.send(
            f"✅ Bylo odstraněno **{len(deleted)}** zpráv.",
            ephemeral=True,
        )

    @app_commands.command(
        name="slowmode",
        description="Nastaví pomalý režim v aktuálním kanálu.",
    )
    @app_commands.describe(seconds="Prodleva v sekundách (0–21600)")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def slowmode(
        self,
        interaction: discord.Interaction,
        seconds: app_commands.Range[int, 0, 21600],
    ):
        if not await self.safe_defer(interaction):
            return

        if not isinstance(interaction.channel, discord.TextChannel):
            await interaction.followup.send(
                "❌ Příkaz lze použít pouze v textovém kanálu.",
                ephemeral=True,
            )
            return

        try:
            await interaction.channel.edit(
                slowmode_delay=seconds,
                reason=f"Nastavil {interaction.user}",
            )
        except discord.Forbidden:
            await interaction.followup.send(
                "❌ Bot nemá oprávnění upravit kanál.",
                ephemeral=True,
            )
            return

        await interaction.followup.send(
            (
                "✅ Pomalý režim byl vypnut."
                if seconds == 0
                else f"✅ Pomalý režim byl nastaven na **{seconds} sekund**."
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
                "Moderation interakce %s vypršela.",
                interaction.id,
            )
            return

        if isinstance(error, app_commands.MissingPermissions):
            missing = ", ".join(error.missing_permissions)
            message = f"❌ Nemáš potřebná oprávnění: `{missing}`"
        else:
            logger.exception("Chyba moderation příkazu: %s", error)
            message = "❌ Nastala chyba při zpracování moderačního příkazu."

        try:
            if interaction.response.is_done():
                await interaction.followup.send(message, ephemeral=True)
            else:
                await interaction.response.send_message(message, ephemeral=True)
        except discord.HTTPException:
            logger.warning(
                "Na moderation interakci %s už nešlo odpovědět.",
                interaction.id,
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(Moderation(bot))
