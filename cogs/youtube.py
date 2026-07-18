import discord
from discord import app_commands
from discord.ext import commands

from config import EMBED_COLOR, EMBED_FOOTER
from utils.database import db
from utils.time_utils import format_discord_time
from utils.views import youtube_video_view
from utils.youtube_api import YouTubeAPIError, youtube_api


def build_video_embed(
    title: str,
    url: str,
    channel_name: str,
    thumbnail: str | None,
    published_at: str | None,
    live: bool = False,
) -> discord.Embed:
    if live:
        embed_title = "🔴 Živý stream"
        description = f"**{channel_name} právě vysílá živě!**\\n\\n**{title}**"
        color = discord.Color.red()
        time_field_name = "Spuštěno"
    else:
        embed_title = "📺 Nové video"
        description = f"**{title}**"
        color = EMBED_COLOR
        time_field_name = "Publikováno"

    embed = discord.Embed(
        title=embed_title,
        description=description,
        url=url,
        color=color,
    )

    embed.add_field(
        name="Kanál",
        value=channel_name,
        inline=False,
    )

    published_text = format_discord_time(published_at)

    if published_text:
        embed.add_field(
            name=time_field_name,
            value=published_text,
            inline=False,
        )

    if thumbnail:
        embed.set_image(url=thumbnail)

    embed.set_footer(text=EMBED_FOOTER)
    return embed


class YouTube(commands.GroupCog, name="youtube"):
    """Slash příkazy pro správu YouTube notifikací."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _subscription_choices(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        if interaction.guild is None:
            return []

        subscriptions = db.get_guild_subscriptions(interaction.guild.id)
        current = current.lower()
        choices: list[app_commands.Choice[str]] = []

        for sub in subscriptions:
            name = sub["youtube_name"]
            channel_id = sub["youtube_channel_id"]

            if not current or current in name.lower() or current in channel_id.lower():
                choices.append(
                    app_commands.Choice(
                        name=name[:100],
                        value=channel_id,
                    )
                )

        return choices[:25]

    def _find_subscription(self, guild_id: int, youtube_channel_id: str):
        subscriptions = db.get_guild_subscriptions(guild_id)

        for sub in subscriptions:
            if sub["youtube_channel_id"] == youtube_channel_id:
                return sub

        return None

    @app_commands.command(
        name="add",
        description="Přidá YouTube kanál ke sledování.",
    )
    @app_commands.describe(
        url="URL YouTube kanálu, např. https://youtube.com/@MrBeast",
        channel="Discord kanál pro oznámení",
        role="Volitelná role pro označení při novém videu",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def add(
        self,
        interaction: discord.Interaction,
        url: str,
        channel: discord.TextChannel,
        role: discord.Role | None = None,
    ):
        await interaction.response.defer(ephemeral=True)

        if interaction.guild is None:
            await interaction.followup.send(
                "❌ Tento příkaz lze použít pouze na serveru.",
                ephemeral=True,
            )
            return

        try:
            yt_channel = await youtube_api.resolve_channel(url)

            db.add_guild(
                guild_id=interaction.guild.id,
                guild_name=interaction.guild.name,
            )

            db.add_youtube_channel(
                channel_id=yt_channel.id,
                name=yt_channel.title,
                url=yt_channel.url,
            )

            db.add_subscription(
                guild_id=interaction.guild.id,
                youtube_channel_id=yt_channel.id,
                discord_channel_id=channel.id,
                mention_role_id=role.id if role else None,
            )

            embed = discord.Embed(
                title="✅ YouTube kanál přidán",
                description=f"**{yt_channel.title}** byl přidán ke sledování.",
                color=EMBED_COLOR,
            )

            embed.add_field(
                name="📺 YouTube",
                value=f"[Otevřít kanál]({yt_channel.url})",
                inline=False,
            )

            embed.add_field(
                name="🆔 Channel ID",
                value=f"`{yt_channel.id}`",
                inline=False,
            )

            embed.add_field(
                name="📢 Discord kanál",
                value=channel.mention,
                inline=True,
            )

            embed.add_field(
                name="👥 Role",
                value=role.mention if role else "Žádná",
                inline=True,
            )

            if yt_channel.thumbnail:
                embed.set_thumbnail(url=yt_channel.thumbnail)

            embed.set_footer(text=EMBED_FOOTER)

            await interaction.followup.send(
                embed=embed,
                ephemeral=True,
            )

        except YouTubeAPIError as e:
            await interaction.followup.send(
                f"❌ YouTube chyba: {e}",
                ephemeral=True,
            )

        except Exception as e:
            await interaction.followup.send(
                f"❌ Neočekávaná chyba:\n```{e}```",
                ephemeral=True,
            )

    @app_commands.command(
        name="list",
        description="Zobrazí sledované YouTube kanály na tomto serveru.",
    )
    async def list(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        if interaction.guild is None:
            await interaction.followup.send(
                "❌ Tento příkaz lze použít pouze na serveru.",
                ephemeral=True,
            )
            return

        subscriptions = db.get_guild_subscriptions(interaction.guild.id)

        if not subscriptions:
            await interaction.followup.send(
                "📭 Tento server zatím nesleduje žádné YouTube kanály.",
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title="📺 Sledované YouTube kanály",
            color=EMBED_COLOR,
        )

        for sub in subscriptions:
            discord_channel = interaction.guild.get_channel(sub["discord_channel_id"])
            role_text = "Žádná"

            if sub["mention_role_id"]:
                role = interaction.guild.get_role(sub["mention_role_id"])
                role_text = role.mention if role else f"`{sub['mention_role_id']}`"

            embed.add_field(
                name=sub["youtube_name"],
                value=(
                    f"🔗 {sub['youtube_url']}\n"
                    f"📢 {discord_channel.mention if discord_channel else 'Neznámý kanál'}\n"
                    f"👥 {role_text}\n"
                    f"{'🟢 Aktivní' if sub['enabled'] else '🔴 Pozastaveno'}"
                ),
                inline=False,
            )

        embed.set_footer(text=f"{EMBED_FOOTER} • Celkem: {len(subscriptions)}")

        await interaction.followup.send(
            embed=embed,
            ephemeral=True,
        )

    @app_commands.command(
        name="remove",
        description="Odebere YouTube kanál ze sledování.",
    )
    @app_commands.describe(
        youtube_channel_id="YouTube kanál k odebrání",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def remove(
        self,
        interaction: discord.Interaction,
        youtube_channel_id: str,
    ):
        await interaction.response.defer(ephemeral=True)

        if interaction.guild is None:
            await interaction.followup.send(
                "❌ Tento příkaz lze použít pouze na serveru.",
                ephemeral=True,
            )
            return

        removed = db.remove_subscription(
            guild_id=interaction.guild.id,
            youtube_channel_id=youtube_channel_id,
        )

        if removed:
            await interaction.followup.send(
                "✅ YouTube kanál byl odebrán ze sledování.",
                ephemeral=True,
            )
        else:
            await interaction.followup.send(
                "❌ Tento kanál nebyl na serveru nalezen.",
                ephemeral=True,
            )

    @remove.autocomplete("youtube_channel_id")
    async def remove_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ):
        return await self._subscription_choices(interaction, current)

    @app_commands.command(
        name="pause",
        description="Pozastaví notifikace pro sledovaný YouTube kanál.",
    )
    @app_commands.describe(
        youtube_channel_id="YouTube kanál k pozastavení",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def pause(
        self,
        interaction: discord.Interaction,
        youtube_channel_id: str,
    ):
        await interaction.response.defer(ephemeral=True)

        if interaction.guild is None:
            await interaction.followup.send(
                "❌ Tento příkaz lze použít pouze na serveru.",
                ephemeral=True,
            )
            return

        sub = self._find_subscription(interaction.guild.id, youtube_channel_id)

        if sub is None:
            await interaction.followup.send(
                "❌ Tento kanál není na serveru sledovaný.",
                ephemeral=True,
            )
            return

        db.pause_subscription(
            guild_id=interaction.guild.id,
            youtube_channel_id=youtube_channel_id,
        )

        await interaction.followup.send(
            f"⏸️ Notifikace pro **{sub['youtube_name']}** byly pozastaveny.",
            ephemeral=True,
        )

    @pause.autocomplete("youtube_channel_id")
    async def pause_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ):
        return await self._subscription_choices(interaction, current)

    @app_commands.command(
        name="resume",
        description="Znovu zapne notifikace pro YouTube kanál.",
    )
    @app_commands.describe(
        youtube_channel_id="YouTube kanál k obnovení",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def resume(
        self,
        interaction: discord.Interaction,
        youtube_channel_id: str,
    ):
        await interaction.response.defer(ephemeral=True)

        if interaction.guild is None:
            await interaction.followup.send(
                "❌ Tento příkaz lze použít pouze na serveru.",
                ephemeral=True,
            )
            return

        sub = self._find_subscription(interaction.guild.id, youtube_channel_id)

        if sub is None:
            await interaction.followup.send(
                "❌ Tento kanál není na serveru sledovaný.",
                ephemeral=True,
            )
            return

        db.resume_subscription(
            guild_id=interaction.guild.id,
            youtube_channel_id=youtube_channel_id,
        )

        await interaction.followup.send(
            f"▶️ Notifikace pro **{sub['youtube_name']}** byly znovu zapnuty.",
            ephemeral=True,
        )

    @resume.autocomplete("youtube_channel_id")
    async def resume_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ):
        return await self._subscription_choices(interaction, current)

    @app_commands.command(
        name="latest",
        description="Zobrazí poslední video sledovaného YouTube kanálu.",
    )
    @app_commands.describe(
        youtube_channel_id="YouTube kanál",
    )
    async def latest(
        self,
        interaction: discord.Interaction,
        youtube_channel_id: str,
    ):
        await interaction.response.defer(ephemeral=True)

        if interaction.guild is None:
            await interaction.followup.send(
                "❌ Tento příkaz lze použít pouze na serveru.",
                ephemeral=True,
            )
            return

        selected = self._find_subscription(
            interaction.guild.id,
            youtube_channel_id,
        )

        if selected is None:
            await interaction.followup.send(
                "❌ Tento kanál není na serveru sledovaný.",
                ephemeral=True,
            )
            return

        latest = await youtube_api.get_latest_video(youtube_channel_id)

        if latest is None:
            await interaction.followup.send(
                "📭 Nepodařilo se najít poslední video.",
                ephemeral=True,
            )
            return

        if latest.live:
            latest_description = (
                f"🔴 **{selected['youtube_name']} právě vysílá živě!**"
            )
            latest_color = discord.Color.red()
        else:
            latest_description = (
                f"Poslední video z kanálu **{selected['youtube_name']}**"
            )
            latest_color = EMBED_COLOR

        embed = discord.Embed(
            title=latest.title,
            url=latest.url,
            description=latest_description,
            color=latest_color,
        )

        if latest.thumbnail:
            embed.set_image(url=latest.thumbnail)

        published_text = format_discord_time(latest.published_at)

        if published_text:
            embed.add_field(
                name="Publikováno",
                value=published_text,
                inline=False,
            )

        embed.set_footer(text=EMBED_FOOTER)

        await interaction.followup.send(
            embed=embed,
            view=youtube_video_view(latest.url),
            ephemeral=True,
        )

    @latest.autocomplete("youtube_channel_id")
    async def latest_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ):
        return await self._subscription_choices(interaction, current)

    @app_commands.command(
        name="info",
        description="Zobrazí nastavení sledovaného YouTube kanálu.",
    )
    @app_commands.describe(
        youtube_channel_id="YouTube kanál",
    )
    async def info(
        self,
        interaction: discord.Interaction,
        youtube_channel_id: str,
    ):
        await interaction.response.defer(ephemeral=True)

        if interaction.guild is None:
            await interaction.followup.send(
                "❌ Tento příkaz lze použít pouze na serveru.",
                ephemeral=True,
            )
            return

        sub = self._find_subscription(
            interaction.guild.id,
            youtube_channel_id,
        )

        if sub is None:
            await interaction.followup.send(
                "❌ Tento kanál není na serveru sledovaný.",
                ephemeral=True,
            )
            return

        discord_channel = interaction.guild.get_channel(sub["discord_channel_id"])
        role_text = "Žádná"

        if sub["mention_role_id"]:
            role = interaction.guild.get_role(sub["mention_role_id"])
            role_text = role.mention if role else f"`{sub['mention_role_id']}`"

        embed = discord.Embed(
            title=f"ℹ️ {sub['youtube_name']}",
            color=EMBED_COLOR,
        )

        embed.add_field(
            name="YouTube",
            value=f"[Otevřít kanál]({sub['youtube_url']})",
            inline=False,
        )

        embed.add_field(
            name="Channel ID",
            value=f"`{sub['youtube_channel_id']}`",
            inline=False,
        )

        embed.add_field(
            name="Discord kanál",
            value=discord_channel.mention if discord_channel else "Neznámý kanál",
            inline=True,
        )

        embed.add_field(
            name="Role",
            value=role_text,
            inline=True,
        )

        embed.add_field(
            name="Stav",
            value="🟢 Aktivní" if sub["enabled"] else "🔴 Pozastaveno",
            inline=True,
        )

        embed.add_field(
            name="Poslední video ID",
            value=f"`{sub['last_video_id']}`" if sub["last_video_id"] else "Zatím žádné",
            inline=False,
        )

        embed.set_footer(text=EMBED_FOOTER)

        await interaction.followup.send(
            embed=embed,
            ephemeral=True,
        )

    @info.autocomplete("youtube_channel_id")
    async def info_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ):
        return await self._subscription_choices(interaction, current)

    @app_commands.command(
        name="test",
        description="Pošle testovací oznámení videa nebo streamu.",
    )
    @app_commands.describe(
        youtube_channel_id="YouTube kanál",
        ping_role="Jestli se má při testu označit nastavená role",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def test(
        self,
        interaction: discord.Interaction,
        youtube_channel_id: str,
        ping_role: bool = False,
    ):
        await interaction.response.defer(ephemeral=True)

        if interaction.guild is None:
            await interaction.followup.send(
                "❌ Tento příkaz lze použít pouze na serveru.",
                ephemeral=True,
            )
            return

        sub = self._find_subscription(
            interaction.guild.id,
            youtube_channel_id,
        )

        if sub is None:
            await interaction.followup.send(
                "❌ Tento kanál není na serveru sledovaný.",
                ephemeral=True,
            )
            return

        discord_channel = interaction.guild.get_channel(sub["discord_channel_id"])

        if discord_channel is None:
            await interaction.followup.send(
                "❌ Nastavený Discord kanál nebyl nalezen.",
                ephemeral=True,
            )
            return

        latest = await youtube_api.get_latest_video(youtube_channel_id)

        if latest is None:
            await interaction.followup.send(
                "📭 Nepodařilo se najít poslední video.",
                ephemeral=True,
            )
            return

        mention = None

        if ping_role and sub["mention_role_id"]:
            mention = f"<@&{sub['mention_role_id']}>"

        embed = build_video_embed(
            title=latest.title,
            url=latest.url,
            channel_name=sub["youtube_name"],
            thumbnail=latest.thumbnail,
            published_at=latest.published_at,
            live=latest.live,
        )

        await discord_channel.send(
            content=mention,
            embed=embed,
            view=youtube_video_view(latest.url),
        )

        await interaction.followup.send(
            f"✅ Testovací oznámení bylo odesláno do {discord_channel.mention}.",
            ephemeral=True,
        )

    @test.autocomplete("youtube_channel_id")
    async def test_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ):
        return await self._subscription_choices(interaction, current)

    @app_commands.command(
        name="check",
        description="Ručně zkontroluje nová videa a živé streamy.",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def check(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        if interaction.guild is None:
            await interaction.followup.send(
                "❌ Tento příkaz lze použít pouze na serveru.",
                ephemeral=True,
            )
            return

        subscriptions = db.get_guild_subscriptions(interaction.guild.id)

        if not subscriptions:
            await interaction.followup.send(
                "📭 Tento server nesleduje žádné YouTube kanály.",
                ephemeral=True,
            )
            return

        found = 0
        sent = 0

        for sub in subscriptions:
            if not sub["enabled"]:
                continue

            latest = await youtube_api.get_latest_video(sub["youtube_channel_id"])

            if latest is None:
                continue

            if sub["last_video_id"] == latest.id:
                continue

            found += 1
            discord_channel = interaction.guild.get_channel(sub["discord_channel_id"])

            if discord_channel:
                mention = f"<@&{sub['mention_role_id']}>" if sub["mention_role_id"] else None
                embed = build_video_embed(
                    title=latest.title,
                    url=latest.url,
                    channel_name=sub["youtube_name"],
                    thumbnail=latest.thumbnail,
                    published_at=latest.published_at,
                )

                await discord_channel.send(
                    content=mention,
                    embed=embed,
                    view=youtube_video_view(latest.url),
                )

                sent += 1

            db.add_video(
                video_id=latest.id,
                youtube_channel_id=sub["youtube_channel_id"],
                title=latest.title,
                url=latest.url,
                published_at=latest.published_at,
            )

            db.set_last_video(
                guild_id=interaction.guild.id,
                youtube_channel_id=sub["youtube_channel_id"],
                video_id=latest.id,
            )

        await interaction.followup.send(
            f"✅ Kontrola dokončena.\nNová videa/streamy: **{found}**\nOdesláno: **{sent}**",
            ephemeral=True,
        )

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
            await interaction.followup.send(
                message,
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                message,
                ephemeral=True,
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(YouTube(bot))
