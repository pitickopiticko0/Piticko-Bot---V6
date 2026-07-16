import discord
from discord import app_commands
from discord.ext import commands

from config import EMBED_COLOR, EMBED_FOOTER
from utils.database import db
from utils.logger import logger


DEFAULT_WELCOME_MESSAGE = "👋 Vítej {user} na serveru **{server}**! Jsi náš {members}. člen."


def render_welcome_message(template: str, member: discord.Member) -> str:
    return (
        template
        .replace("{user}", member.mention)
        .replace("{username}", member.name)
        .replace("{server}", member.guild.name)
        .replace("{members}", str(member.guild.member_count or 0))
    )


def build_welcome_embed(member: discord.Member, message: str) -> discord.Embed:
    embed = discord.Embed(
        title="🎉 Nový člen!",
        description=message,
        color=EMBED_COLOR,
    )
    embed.add_field(name="Uživatel", value=f"{member.mention}\n`{member.id}`", inline=False)
    embed.add_field(name="Server", value=member.guild.name, inline=True)
    embed.add_field(name="Členů", value=str(member.guild.member_count or 0), inline=True)
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.set_footer(text=EMBED_FOOTER)
    return embed


class Welcome(commands.GroupCog, name="welcome"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def get_welcome_channel(self, guild: discord.Guild, channel_id: int):
        channel = guild.get_channel(channel_id)

        if channel is not None:
            return channel

        try:
            channel = await guild.fetch_channel(channel_id)
            return channel
        except discord.NotFound:
            logger.warning("Welcome kanál %s nebyl nalezen na serveru %s.", channel_id, guild.id)
        except discord.Forbidden:
            logger.warning("Bot nemá oprávnění načíst welcome kanál %s na serveru %s.", channel_id, guild.id)
        except Exception:
            logger.exception("Chyba při načítání welcome kanálu %s na serveru %s.", channel_id, guild.id)

        return None

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        logger.info(
            "WELCOME JOIN EVENT: %s (%s) na serveru %s (%s)",
            member.name,
            member.id,
            member.guild.name,
            member.guild.id,
        )

        try:
            settings = db.get_welcome_settings(member.guild.id)
        except Exception:
            logger.exception("Nepodařilo se načíst welcome nastavení pro server %s.", member.guild.id)
            return

        if settings is None:
            logger.info("Welcome není nastavený pro server %s.", member.guild.id)
            return

        logger.info(
            "Welcome settings: guild=%s channel=%s role=%s enabled=%s",
            settings["guild_id"],
            settings["channel_id"],
            settings["role_id"],
            settings["enabled"],
        )

        if not settings["enabled"]:
            logger.info("Welcome je vypnutý pro server %s.", member.guild.id)
            return

        channel = await self.get_welcome_channel(member.guild, int(settings["channel_id"]))

        if channel is None:
            return

        if settings["role_id"]:
            role = member.guild.get_role(int(settings["role_id"]))

            if role is None:
                logger.warning("Welcome role %s nebyla nalezena na serveru %s.", settings["role_id"], member.guild.id)
            else:
                try:
                    await member.add_roles(role, reason="Piticko Bot welcome role")
                    logger.info("Welcome role %s přidána uživateli %s.", role.id, member.id)
                except discord.Forbidden:
                    logger.warning("Bot nemá oprávnění přidat roli %s na serveru %s.", role.id, member.guild.id)
                except Exception:
                    logger.exception("Nepodařilo se přidat welcome roli na serveru %s.", member.guild.id)

        message = render_welcome_message(settings["message"], member)
        embed = build_welcome_embed(member, message)

        try:
            await channel.send(embed=embed)
            logger.info("Welcome zpráva odeslána do kanálu %s pro uživatele %s.", channel.id, member.id)
        except discord.Forbidden:
            logger.warning("Bot nemá oprávnění poslat zprávu do kanálu %s.", channel.id)
        except Exception:
            logger.exception("Nepodařilo se odeslat welcome zprávu do kanálu %s.", channel.id)

    @app_commands.command(name="setup", description="Nastaví welcome zprávy pro tento server.")
    @app_commands.describe(
        channel="Kanál, kam se pošle welcome zpráva",
        role="Volitelná role, kterou bot přidá novému členovi",
        message="Vlastní zpráva. Podporuje {user}, {username}, {server}, {members}",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def setup(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        role: discord.Role | None = None,
        message: str = DEFAULT_WELCOME_MESSAGE,
    ):
        await interaction.response.defer(ephemeral=True)

        if interaction.guild is None:
            await interaction.followup.send("❌ Tento příkaz lze použít pouze na serveru.", ephemeral=True)
            return

        db.add_guild(interaction.guild.id, interaction.guild.name)
        db.set_welcome_settings(
            guild_id=interaction.guild.id,
            channel_id=channel.id,
            role_id=role.id if role else None,
            message=message,
        )

        embed = discord.Embed(title="✅ Welcome systém nastaven", color=EMBED_COLOR)
        embed.add_field(name="Kanál", value=channel.mention, inline=True)
        embed.add_field(name="Role", value=role.mention if role else "Žádná", inline=True)
        embed.add_field(name="Zpráva", value=message, inline=False)
        embed.set_footer(text=EMBED_FOOTER)

        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="info", description="Zobrazí aktuální welcome nastavení.")
    async def info(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        if interaction.guild is None:
            await interaction.followup.send("❌ Tento příkaz lze použít pouze na serveru.", ephemeral=True)
            return

        settings = db.get_welcome_settings(interaction.guild.id)

        if settings is None:
            await interaction.followup.send("📭 Welcome systém zatím není nastavený.", ephemeral=True)
            return

        channel = interaction.guild.get_channel(int(settings["channel_id"])) if settings["channel_id"] else None
        role = interaction.guild.get_role(int(settings["role_id"])) if settings["role_id"] else None

        embed = discord.Embed(title="👋 Welcome nastavení", color=EMBED_COLOR)
        embed.add_field(name="Stav", value="🟢 Zapnuto" if settings["enabled"] else "🔴 Vypnuto", inline=True)
        embed.add_field(name="Kanál", value=channel.mention if channel else "Nenalezen", inline=True)
        embed.add_field(name="Role", value=role.mention if role else "Žádná", inline=True)
        embed.add_field(name="Zpráva", value=settings["message"], inline=False)
        embed.set_footer(text=EMBED_FOOTER)

        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="disable", description="Vypne welcome zprávy pro tento server.")
    @app_commands.checks.has_permissions(administrator=True)
    async def disable(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        if interaction.guild is None:
            await interaction.followup.send("❌ Tento příkaz lze použít pouze na serveru.", ephemeral=True)
            return

        db.disable_welcome(interaction.guild.id)
        await interaction.followup.send("✅ Welcome systém byl vypnut.", ephemeral=True)

    @app_commands.command(name="test", description="Pošle testovací welcome zprávu.")
    @app_commands.checks.has_permissions(administrator=True)
    async def test(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            await interaction.followup.send("❌ Tento příkaz lze použít pouze na serveru.", ephemeral=True)
            return

        settings = db.get_welcome_settings(interaction.guild.id)

        if settings is None or not settings["enabled"]:
            await interaction.followup.send("❌ Welcome systém není zapnutý.", ephemeral=True)
            return

        channel = await self.get_welcome_channel(interaction.guild, int(settings["channel_id"]))

        if channel is None:
            await interaction.followup.send("❌ Welcome kanál nebyl nalezen.", ephemeral=True)
            return

        message = render_welcome_message(settings["message"], interaction.user)
        embed = build_welcome_embed(interaction.user, message)

        await channel.send(embed=embed)
        await interaction.followup.send(f"✅ Testovací welcome zpráva byla odeslána do {channel.mention}.", ephemeral=True)

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
    await bot.add_cog(Welcome(bot))
