import discord
from discord import app_commands
from discord.ext import commands

from config import EMBED_COLOR, EMBED_FOOTER
from utils.database import db
from utils.logger import logger


class AutoRole(commands.GroupCog, name="autorole"):
    """Automatické přidávání role novým členům."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._init_table()

    def _init_table(self) -> None:
        with db.connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS autorole_settings (
                    guild_id BIGINT PRIMARY KEY,
                    role_id BIGINT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    updated_at TEXT NOT NULL
                )
            """)
            conn.commit()

    def get_settings(self, guild_id: int):
        with db.connect() as conn:
            return conn.execute("""
                SELECT *
                FROM autorole_settings
                WHERE guild_id = ?
            """, (guild_id,)).fetchone()

    def save_settings(self, guild_id: int, role_id: int) -> None:
        with db.connect() as conn:
            if db.using_postgres:
                conn.execute("""
                    INSERT INTO autorole_settings
                    (guild_id, role_id, enabled, updated_at)
                    VALUES (?, ?, 1, ?)
                    ON CONFLICT (guild_id)
                    DO UPDATE SET
                        role_id = EXCLUDED.role_id,
                        enabled = 1,
                        updated_at = EXCLUDED.updated_at
                """, (guild_id, role_id, db.now()))
            else:
                conn.execute("""
                    INSERT OR REPLACE INTO autorole_settings
                    (guild_id, role_id, enabled, updated_at)
                    VALUES (?, ?, 1, ?)
                """, (guild_id, role_id, db.now()))

            conn.commit()

    def disable_settings(self, guild_id: int) -> None:
        with db.connect() as conn:
            conn.execute("""
                UPDATE autorole_settings
                SET enabled = 0,
                    updated_at = ?
                WHERE guild_id = ?
            """, (db.now(), guild_id))
            conn.commit()

    async def safe_defer(self, interaction: discord.Interaction) -> bool:
        """
        Pokusí se potvrdit Discord interakci.
        Vrátí False, pokud interakce vypršela nebo už není dostupná.
        """
        try:
            await interaction.response.defer(ephemeral=True)
            return True
        except discord.NotFound:
            logger.warning(
                "Discord interakce %s vypršela nebo už není dostupná.",
                interaction.id,
            )
            return False
        except discord.HTTPException as error:
            logger.warning(
                "Nepodařilo se potvrdit Discord interakci %s: %s",
                interaction.id,
                error,
            )
            return False

    @app_commands.command(
        name="setup",
        description="Nastaví automatickou roli pro nové členy.",
    )
    @app_commands.describe(
        role="Role, kterou bot automaticky přidá novým členům",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def setup(
        self,
        interaction: discord.Interaction,
        role: discord.Role,
    ):
        if not await self.safe_defer(interaction):
            return

        if interaction.guild is None:
            await interaction.followup.send(
                "❌ Tento příkaz lze použít pouze na serveru.",
                ephemeral=True,
            )
            return

        if role.is_default():
            await interaction.followup.send(
                "❌ Nelze použít roli @everyone.",
                ephemeral=True,
            )
            return

        if role.managed:
            await interaction.followup.send(
                "❌ Tuto roli spravuje integrace nebo jiný bot.",
                ephemeral=True,
            )
            return

        bot_member = interaction.guild.me

        if bot_member is None:
            await interaction.followup.send(
                "❌ Nepodařilo se načíst roli bota.",
                ephemeral=True,
            )
            return

        if not bot_member.guild_permissions.manage_roles:
            await interaction.followup.send(
                "❌ Bot nemá oprávnění **Spravovat role**.",
                ephemeral=True,
            )
            return

        if role >= bot_member.top_role:
            await interaction.followup.send(
                "❌ Role bota musí být v seznamu rolí výše než vybraná AutoRole.",
                ephemeral=True,
            )
            return

        db.add_guild(interaction.guild.id, interaction.guild.name)
        self.save_settings(interaction.guild.id, role.id)

        embed = discord.Embed(
            title="✅ AutoRole nastavena",
            color=EMBED_COLOR,
        )
        embed.add_field(name="Role", value=role.mention, inline=False)
        embed.add_field(name="Stav", value="🟢 Zapnuto", inline=False)
        embed.set_footer(text=EMBED_FOOTER)

        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(
        name="info",
        description="Zobrazí aktuální nastavení AutoRole.",
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
                "📭 AutoRole zatím není nastavena.",
                ephemeral=True,
            )
            return

        role = interaction.guild.get_role(int(settings["role_id"]))

        embed = discord.Embed(
            title="🎭 AutoRole nastavení",
            color=EMBED_COLOR,
        )
        embed.add_field(
            name="Stav",
            value="🟢 Zapnuto" if settings["enabled"] else "🔴 Vypnuto",
            inline=True,
        )
        embed.add_field(
            name="Role",
            value=role.mention if role else f"Nenalezena (`{settings['role_id']}`)",
            inline=True,
        )
        embed.set_footer(text=EMBED_FOOTER)

        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(
        name="disable",
        description="Vypne automatické přidávání role.",
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
            "✅ AutoRole byla vypnuta.",
            ephemeral=True,
        )

    @app_commands.command(
        name="test",
        description="Přidá AutoRole tobě jako test.",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def test(self, interaction: discord.Interaction):
        if not await self.safe_defer(interaction):
            return

        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            await interaction.followup.send(
                "❌ Tento příkaz lze použít pouze na serveru.",
                ephemeral=True,
            )
            return

        settings = self.get_settings(interaction.guild.id)

        if settings is None or not settings["enabled"]:
            await interaction.followup.send(
                "❌ AutoRole není zapnutá.",
                ephemeral=True,
            )
            return

        role = interaction.guild.get_role(int(settings["role_id"]))

        if role is None:
            await interaction.followup.send(
                "❌ Nastavená role už na serveru neexistuje.",
                ephemeral=True,
            )
            return

        bot_member = interaction.guild.me

        if bot_member is None or role >= bot_member.top_role:
            await interaction.followup.send(
                "❌ Role bota musí být výše než nastavená AutoRole.",
                ephemeral=True,
            )
            return

        try:
            await interaction.user.add_roles(
                role,
                reason="Piticko Bot AutoRole test",
            )
        except discord.Forbidden:
            await interaction.followup.send(
                "❌ Bot nemá oprávnění tuto roli přidat. "
                "Přesuň roli bota výše než AutoRole.",
                ephemeral=True,
            )
            return
        except discord.HTTPException as error:
            logger.exception("Discord chyba při testu AutoRole: %s", error)
            await interaction.followup.send(
                "❌ Discord odmítl přidání role.",
                ephemeral=True,
            )
            return

        await interaction.followup.send(
            f"✅ Role {role.mention} ti byla přidána.",
            ephemeral=True,
        )

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        try:
            settings = self.get_settings(member.guild.id)

            if settings is None or not settings["enabled"]:
                return

            role = member.guild.get_role(int(settings["role_id"]))

            if role is None:
                logger.warning(
                    "AutoRole %s nebyla nalezena na serveru %s.",
                    settings["role_id"],
                    member.guild.id,
                )
                return

            bot_member = member.guild.me

            if bot_member is None or not bot_member.guild_permissions.manage_roles:
                logger.warning(
                    "Bot nemá oprávnění Spravovat role na serveru %s.",
                    member.guild.id,
                )
                return

            if role >= bot_member.top_role:
                logger.warning(
                    "AutoRole %s je výše nebo stejně vysoko jako role bota "
                    "na serveru %s.",
                    role.id,
                    member.guild.id,
                )
                return

            await member.add_roles(
                role,
                reason="Piticko Bot AutoRole",
            )

            logger.info(
                "AutoRole %s přidána uživateli %s na serveru %s.",
                role.id,
                member.id,
                member.guild.id,
            )

        except discord.Forbidden:
            logger.warning(
                "Bot nemá oprávnění přidat AutoRole uživateli %s "
                "na serveru %s.",
                member.id,
                member.guild.id,
            )
        except Exception:
            logger.exception(
                "Chyba AutoRole pro uživatele %s na serveru %s.",
                member.id,
                member.guild.id,
            )

    async def cog_app_command_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ):
        original = getattr(error, "original", error)

        if isinstance(original, discord.NotFound):
            logger.warning(
                "Discord interakce %s vypršela nebo už není dostupná.",
                interaction.id,
            )
            return

        if isinstance(error, app_commands.MissingPermissions):
            message = "❌ Tento příkaz může použít pouze administrátor."
        else:
            logger.exception("Chyba AutoRole příkazu: %s", error)
            message = "❌ Nastala chyba při zpracování příkazu."

        try:
            if interaction.response.is_done():
                await interaction.followup.send(message, ephemeral=True)
            else:
                await interaction.response.send_message(message, ephemeral=True)
        except discord.NotFound:
            logger.warning(
                "Na Discord interakci %s už nebylo možné odpovědět.",
                interaction.id,
            )
        except discord.HTTPException as response_error:
            logger.warning(
                "Discord odmítl odpověď na AutoRole interakci %s: %s",
                interaction.id,
                response_error,
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(AutoRole(bot))
