"""Komunitní hra, ve které členové postupně počítají ovečky."""

import asyncio
import time

import discord
from discord import app_commands
from discord.ext import commands

from utils.database import db
from utils.logger import logger


class SheepGame(commands.GroupCog, group_name="ovecky"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._settings_cache: dict[int, tuple[float, object | None]] = {}
        self._locks: dict[int, asyncio.Lock] = {}

    def _settings(self, guild_id: int, *, refresh: bool = False):
        cached = self._settings_cache.get(guild_id)
        now = time.monotonic()
        if not refresh and cached and now - cached[0] < 5:
            return cached[1]
        settings = db.get_sheep_game_settings(guild_id)
        self._settings_cache[guild_id] = (now, settings)
        return settings

    def _clear_cache(self, guild_id: int) -> None:
        self._settings_cache.pop(guild_id, None)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.guild is None or message.author.bot:
            return
        settings = self._settings(message.guild.id)
        if (
            settings is None
            or not settings["enabled"]
            or not settings["channel_id"]
            or message.channel.id != int(settings["channel_id"])
        ):
            return

        content = message.content.strip()
        if not content.isdecimal() or len(content) > 12:
            await self._remove_invalid(message, "Napiš pouze další číslo v pořadí.")
            return

        lock = self._locks.setdefault(message.guild.id, asyncio.Lock())
        async with lock:
            settings = self._settings(message.guild.id, refresh=True)
            if settings is None or not settings["enabled"]:
                return
            current = int(settings["current_count"] or 0)
            expected = current + 1
            number = int(content)
            same_user = (
                settings["last_user_id"] is not None
                and int(settings["last_user_id"]) == message.author.id
            )

            if number != expected or same_user:
                previous = db.break_sheep_chain(message.guild.id, message.author.id)
                self._clear_cache(message.guild.id)
                reason = (
                    "Jeden člen nesmí počítat dvakrát za sebou."
                    if same_user
                    else f"Mělo následovat číslo **{expected}**."
                )
                await self._remove_invalid(message, reason)
                await message.channel.send(
                    f"💤 {message.author.mention} přerušil počítání na čísle "
                    f"**{previous}**. {reason}\nNový řetězec začíná zase od **1**.",
                    allowed_mentions=discord.AllowedMentions(users=True),
                    delete_after=12,
                )
                return

            db.record_sheep_count(
                message.guild.id, message.author.id, number
            )
            self._clear_cache(message.guild.id)
            try:
                await message.add_reaction("🐑")
            except discord.HTTPException:
                pass
            if number % 100 == 0:
                await message.channel.send(
                    f"🎉 Společně jste napočítali už **{number} oveček**!"
                )

    @staticmethod
    async def _remove_invalid(
        message: discord.Message, reason: str, *, delete: bool = True
    ) -> None:
        if delete:
            try:
                await message.delete()
            except discord.HTTPException:
                pass
        elif reason:
            try:
                await message.add_reaction("❌")
            except discord.HTTPException:
                pass

    @app_commands.command(name="stav", description="Ukáže stav počítání oveček.")
    async def status(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "❌ Příkaz funguje pouze na serveru.", ephemeral=True
            )
            return
        settings = self._settings(interaction.guild.id, refresh=True)
        if settings is None or not settings["enabled"]:
            await interaction.response.send_message(
                "🐑 Počítání oveček není na tomto serveru zapnuté.", ephemeral=True
            )
            return
        embed = discord.Embed(title="🐑 Počítání oveček", color=discord.Color.green())
        embed.add_field(name="Aktuálně", value=str(settings["current_count"]), inline=True)
        embed.add_field(name="Rekord", value=str(settings["record_count"]), inline=True)
        embed.add_field(
            name="Celkem správných čísel",
            value=str(settings["total_valid_counts"]),
            inline=True,
        )
        embed.add_field(
            name="Kanál", value=f"<#{settings['channel_id']}>", inline=False
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(
        name="zebricek", description="Ukáže nejlepší počtáře oveček."
    )
    async def leaderboard(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "❌ Příkaz funguje pouze na serveru.", ephemeral=True
            )
            return
        rows = db.get_sheep_leaderboard(interaction.guild.id, 10)
        if not rows:
            await interaction.response.send_message(
                "🐑 Zatím nikdo nenapočítal žádnou ovečku."
            )
            return
        lines = [
            f"**{index}.** <@{row['user_id']}> — **{row['valid_counts']}** oveček "
            f"· přerušení: {row['chains_broken']}"
            for index, row in enumerate(rows, 1)
        ]
        await interaction.response.send_message(
            embed=discord.Embed(
                title="🏆 Nejlepší počtáři oveček",
                description="\n".join(lines),
                color=discord.Color.gold(),
            )
        )

    @app_commands.command(
        name="nastavit", description="Nastaví kanál pro počítání oveček."
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def configure(
        self, interaction: discord.Interaction, kanal: discord.TextChannel
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "❌ Příkaz funguje pouze na serveru.", ephemeral=True
            )
            return
        permissions = kanal.permissions_for(interaction.guild.me)
        if not (
            permissions.view_channel
            and permissions.send_messages
            and permissions.read_message_history
        ):
            await interaction.response.send_message(
                "❌ Bot v tomto kanálu potřebuje oprávnění zobrazit kanál, "
                "číst historii a posílat zprávy.",
                ephemeral=True,
            )
            return
        previous = db.get_sheep_game_settings(interaction.guild.id)
        db.set_sheep_game_settings(interaction.guild.id, kanal.id, True)
        if previous is not None and previous["channel_id"] != kanal.id:
            db.reset_sheep_chain(interaction.guild.id)
        self._clear_cache(interaction.guild.id)
        warning = ""
        if not permissions.manage_messages or not permissions.add_reactions:
            warning = (
                "\n⚠️ Pro úplnou funkčnost dej botovi také oprávnění "
                "**Spravovat zprávy** a **Přidávat reakce**."
            )
        await interaction.response.send_message(
            f"✅ Počítání oveček je zapnuté v {kanal.mention}. "
            f"Začněte číslem **1**.{warning}"
        )

    @app_commands.command(name="reset", description="Vynuluje aktuální řetězec.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def reset(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "❌ Příkaz funguje pouze na serveru.", ephemeral=True
            )
            return
        db.reset_sheep_chain(interaction.guild.id)
        self._clear_cache(interaction.guild.id)
        await interaction.response.send_message(
            "🔄 Počítání oveček bylo vynulováno. Další číslo je **1**."
        )

    @app_commands.command(name="vypnout", description="Vypne počítání oveček.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def disable(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "❌ Příkaz funguje pouze na serveru.", ephemeral=True
            )
            return
        settings = db.get_sheep_game_settings(interaction.guild.id)
        channel_id = int(settings["channel_id"]) if settings and settings["channel_id"] else None
        db.set_sheep_game_settings(interaction.guild.id, channel_id, False)
        self._clear_cache(interaction.guild.id)
        await interaction.response.send_message("✅ Počítání oveček bylo vypnuto.")

    async def cog_app_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        logger.warning("Chyba příkazu oveček: %s", error)
        if interaction.response.is_done():
            return
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message(
                "❌ Tento příkaz může použít pouze správce serveru.", ephemeral=True
            )
            return
        await interaction.response.send_message(
            "❌ Příkaz se nepodařilo zpracovat.", ephemeral=True
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(SheepGame(bot))
