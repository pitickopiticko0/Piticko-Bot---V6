from __future__ import annotations

import re

import discord
from discord import app_commands
from discord.ext import commands

from config import EMBED_COLOR, EMBED_FOOTER
from utils.logger import logger


def parse_color(value: str | None) -> int:
    if not value:
        return EMBED_COLOR
    cleaned = value.strip().removeprefix("#")
    if not re.fullmatch(r"[0-9a-fA-F]{6}", cleaned):
        raise ValueError("Barva musí mít formát #RRGGBB, například #5865F2.")
    return int(cleaned, 16)


class WebhookCommands(commands.GroupCog, group_name="webhook"):
    """Bezpečné odesílání zpráv přes webhook bez sdílení jeho URL."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="odeslat", description="Odešle zprávu do kanálu přes webhook.")
    @app_commands.describe(
        channel="Kanál, do kterého se zpráva odešle",
        zprava="Text zprávy nebo popis embedu",
        nazev="Jméno zobrazené u webhooku",
        nadpis="Volitelný nadpis – jeho vyplnění vytvoří embed",
        barva="Barva embedu ve formátu #RRGGBB",
    )
    @app_commands.checks.has_permissions(manage_webhooks=True)
    @app_commands.checks.bot_has_permissions(manage_webhooks=True)
    async def send(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        zprava: app_commands.Range[str, 1, 2000],
        nazev: app_commands.Range[str, 1, 80] = "Piticko Webhook",
        nadpis: app_commands.Range[str, 1, 256] | None = None,
        barva: app_commands.Range[str, 4, 7] | None = None,
    ) -> None:
        if interaction.guild is None or channel.guild.id != interaction.guild.id:
            await interaction.response.send_message("❌ Kanál nepatří k tomuto serveru.", ephemeral=True)
            return

        bot_member = interaction.guild.me
        if bot_member is None:
            await interaction.response.send_message("❌ Nepodařilo se načíst oprávnění bota.", ephemeral=True)
            return
        permissions = channel.permissions_for(bot_member)
        if not (permissions.view_channel and permissions.manage_webhooks):
            await interaction.response.send_message(
                "❌ Bot v cílovém kanálu potřebuje oprávnění **Spravovat webhooky**.", ephemeral=True,
            )
            return

        try:
            embed_color = parse_color(barva)
        except ValueError as error:
            await interaction.response.send_message(f"❌ {error}", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        try:
            webhook = next(
                (item for item in await channel.webhooks() if item.user == bot_member and item.name == "Piticko Bot Dashboard"),
                None,
            )
            if webhook is None:
                webhook = await channel.create_webhook(
                    name="Piticko Bot Dashboard",
                    reason=f"Webhook vytvořil {interaction.user} přes Piticko Bot",
                )

            embed = None
            content = zprava
            if nadpis:
                embed = discord.Embed(title=nadpis, description=zprava, color=embed_color)
                embed.set_footer(text=EMBED_FOOTER)
                content = None

            avatar_url = self.bot.user.display_avatar.url if self.bot.user else None
            await webhook.send(
                content=content,
                embed=embed,
                username=nazev,
                avatar_url=avatar_url,
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except discord.Forbidden:
            await interaction.followup.send("❌ Discord odmítl vytvoření nebo použití webhooku.", ephemeral=True)
            return
        except discord.HTTPException:
            logger.exception("Odeslání webhooku do kanálu %s selhalo.", channel.id)
            await interaction.followup.send("❌ Zprávu se nepodařilo odeslat.", ephemeral=True)
            return

        await interaction.followup.send(f"✅ Zpráva byla odeslána do {channel.mention}.", ephemeral=True)

    async def cog_app_command_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        if isinstance(error, app_commands.MissingPermissions):
            message = "❌ Potřebuješ oprávnění **Spravovat webhooky**."
        elif isinstance(error, app_commands.BotMissingPermissions):
            message = "❌ Bot potřebuje oprávnění **Spravovat webhooky**."
        else:
            logger.exception("Chyba webhook příkazu: %s", error)
            message = "❌ Při zpracování webhooku nastala chyba."

        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(WebhookCommands(bot))
