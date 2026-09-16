"""Přehrávání jednotlivých YouTube a YouTube Music odkazů ve voice kanálu."""

from __future__ import annotations

import asyncio
from contextlib import suppress
import logging
import shutil
from collections import deque
from dataclasses import dataclass, field
from typing import Deque
from urllib.parse import urlparse

import discord
import yt_dlp
from discord import app_commands
from discord.ext import commands


logger = logging.getLogger(__name__)

SUPPORTED_HOSTS = {
    "youtube.com",
    "youtu.be",
    "music.youtube.com",
    "www.youtube.com",
    "www.youtu.be",
}
MAX_QUEUE_SIZE = 25

YTDL_OPTIONS = {
    "format": "bestaudio/best",
    "noplaylist": True,
    "quiet": True,
    "no_warnings": True,
    "nocheckcertificate": False,
}

FFMPEG_BEFORE_OPTIONS = "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5"
FFMPEG_OPTIONS = "-vn"


class MusicError(ValueError):
    """Chyba, kterou lze bezpečně ukázat uživateli Discordu."""


@dataclass(slots=True)
class Track:
    title: str
    webpage_url: str
    stream_url: str
    duration_seconds: int | None


@dataclass(slots=True)
class GuildPlayer:
    queue: Deque[Track] = field(default_factory=deque)
    current: Track | None = None
    task: asyncio.Task[None] | None = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


def _is_supported_url(value: str) -> bool:
    parsed = urlparse(value.strip())
    host = (parsed.hostname or "").lower().rstrip(".")
    return parsed.scheme in {"https", "http"} and host in SUPPORTED_HOSTS


def _format_duration(seconds: int | None) -> str:
    if not seconds:
        return "živě nebo neznámá délka"
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes}:{seconds:02d}"


def _extract_track(url: str) -> Track:
    """Vyžádá dočasnou audio adresu. Běží mimo asyncio event loop."""
    try:
        with yt_dlp.YoutubeDL(YTDL_OPTIONS) as ydl:
            info = ydl.extract_info(url, download=False)
    except yt_dlp.utils.DownloadError as error:
        raise MusicError("Odkaz se nepodařilo načíst. Zkus veřejné video nebo skladbu.") from error
    except Exception as error:
        logger.exception("Nepodařilo se získat audio z odkazu %s", url)
        raise MusicError("Při načítání odkazu nastala chyba.") from error

    if not info or not isinstance(info, dict):
        raise MusicError("Pro tento odkaz nebylo nalezeno přehratelné audio.")

    if info.get("entries"):
        raise MusicError("Playlisty zatím nejsou podporované. Pošli odkaz na jednu skladbu nebo video.")

    stream_url = info.get("url")
    if not stream_url:
        raise MusicError("Pro tento odkaz nebylo dostupné audio.")

    return Track(
        title=str(info.get("title") or "Neznámá skladba")[:200],
        webpage_url=str(info.get("webpage_url") or url),
        stream_url=str(stream_url),
        duration_seconds=info.get("duration"),
    )


class Music(commands.GroupCog, group_name="hudba"):
    """Slash příkazy pro jednoduché přehrávání hudby ve voice kanálu."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.players: dict[int, GuildPlayer] = {}

    def cog_unload(self) -> None:
        for player in self.players.values():
            if player.task and not player.task.done():
                player.task.cancel()

    def _player(self, guild_id: int) -> GuildPlayer:
        return self.players.setdefault(guild_id, GuildPlayer())

    @staticmethod
    def _user_voice_channel(
        interaction: discord.Interaction,
    ) -> discord.VoiceChannel | discord.StageChannel | None:
        if not isinstance(interaction.user, discord.Member):
            return None
        return interaction.user.voice.channel if interaction.user.voice else None

    async def _connect_to_user(
        self,
        interaction: discord.Interaction,
    ) -> discord.VoiceClient:
        if interaction.guild is None:
            raise MusicError("Tento příkaz funguje pouze na Discord serveru.")

        channel = self._user_voice_channel(interaction)
        if channel is None:
            raise MusicError("Nejdřív se připoj do voice kanálu.")

        me = interaction.guild.me
        if me is None:
            raise MusicError("Nepodařilo se ověřit oprávnění bota.")

        permissions = channel.permissions_for(me)
        if not permissions.connect or not permissions.speak:
            raise MusicError("Bot potřebuje ve voice kanálu oprávnění Připojit se a Mluvit.")

        voice = interaction.guild.voice_client
        if voice and voice.is_connected():
            if voice.channel != channel:
                raise MusicError(f"Bot už přehrává v kanálu **{voice.channel}**.")
            return voice

        try:
            return await channel.connect(self_deaf=True)
        except discord.ClientException as error:
            raise MusicError("Bot se do voice kanálu nedokázal připojit.") from error

    async def _require_same_channel(
        self,
        interaction: discord.Interaction,
    ) -> discord.VoiceClient:
        if interaction.guild is None:
            raise MusicError("Tento příkaz funguje pouze na Discord serveru.")

        voice = interaction.guild.voice_client
        user_channel = self._user_voice_channel(interaction)
        if not voice or not voice.is_connected():
            raise MusicError("Bot teď nic nepřehrává.")
        if user_channel is None or voice.channel != user_channel:
            raise MusicError("Musíš být ve stejném voice kanálu jako bot.")
        return voice

    async def _run_player(self, guild: discord.Guild, player: GuildPlayer) -> None:
        try:
            while True:
                async with player.lock:
                    if not player.queue:
                        player.current = None
                        player.task = None
                        return
                    track = player.queue.popleft()
                    player.current = track

                voice = guild.voice_client
                if not voice or not voice.is_connected():
                    return

                finished: asyncio.Future[None] = asyncio.get_running_loop().create_future()
                loop = asyncio.get_running_loop()

                def after_playback(error: Exception | None) -> None:
                    if error:
                        logger.warning("Přehrávání '%s' selhalo: %s", track.title, error)

                    def mark_finished() -> None:
                        if not finished.done():
                            finished.set_result(None)

                    loop.call_soon_threadsafe(mark_finished)

                try:
                    source = discord.FFmpegPCMAudio(
                        track.stream_url,
                        before_options=FFMPEG_BEFORE_OPTIONS,
                        options=FFMPEG_OPTIONS,
                    )
                    voice.play(source, after=after_playback)
                except Exception:
                    logger.exception("Nepodařilo se spustit FFmpeg pro '%s'", track.title)
                    if not finished.done():
                        finished.set_result(None)

                await finished
                player.current = None
        except asyncio.CancelledError:
            raise
        finally:
            player.current = None
            if player.task is asyncio.current_task():
                player.task = None

            voice = guild.voice_client
            if voice and voice.is_connected() and not voice.is_playing():
                try:
                    await voice.disconnect()
                except discord.HTTPException:
                    logger.warning("Bot se nepodařilo odpojit z voice kanálu serveru %s", guild.id)

    async def _add_track(self, guild: discord.Guild, track: Track) -> tuple[int, bool]:
        player = self._player(guild.id)
        async with player.lock:
            if len(player.queue) >= MAX_QUEUE_SIZE:
                raise MusicError(f"Fronta může mít maximálně {MAX_QUEUE_SIZE} skladeb.")

            player.queue.append(track)
            position = len(player.queue) + (1 if player.current else 0)
            should_start = player.task is None or player.task.done()
            if should_start:
                player.task = asyncio.create_task(
                    self._run_player(guild, player),
                    name=f"music-player-{guild.id}",
                )
            return position, should_start

    @app_commands.command(name="play", description="Přehraje YouTube nebo YouTube Music odkaz.")
    @app_commands.describe(odkaz="Odkaz na jedno YouTube video nebo skladbu z YouTube Music")
    async def play(self, interaction: discord.Interaction, odkaz: str) -> None:
        if interaction.guild is None:
            await interaction.response.send_message("❌ Použij tento příkaz na serveru.", ephemeral=True)
            return
        if not _is_supported_url(odkaz):
            await interaction.response.send_message(
                "❌ Pošli platný odkaz z **YouTube** nebo **YouTube Music**.",
                ephemeral=True,
            )
            return
        if shutil.which("ffmpeg") is None:
            await interaction.response.send_message(
                "❌ Na VPS chybí FFmpeg. Správce ho musí nejdřív nainstalovat.",
                ephemeral=True,
            )
            return

        await interaction.response.defer()
        try:
            track = await asyncio.to_thread(_extract_track, odkaz)
            await self._connect_to_user(interaction)
            position, starts_now = await self._add_track(interaction.guild, track)
        except MusicError as error:
            await interaction.followup.send(f"❌ {error}")
            return

        if starts_now:
            message = f"▶️ Přehrávám: **[{track.title}]({track.webpage_url})**"
        else:
            message = f"➕ Přidáno do fronty na pozici **{position}**: **[{track.title}]({track.webpage_url})**"
        await interaction.followup.send(f"{message}\nDélka: `{_format_duration(track.duration_seconds)}`")

    @app_commands.command(name="fronta", description="Ukáže aktuální hudební frontu.")
    async def queue(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message("❌ Použij tento příkaz na serveru.", ephemeral=True)
            return

        player = self._player(interaction.guild.id)
        lines: list[str] = []
        if player.current:
            lines.append(f"▶️ Teď: **{player.current.title}**")
        lines.extend(
            f"{index}. {track.title} (`{_format_duration(track.duration_seconds)}`)"
            for index, track in enumerate(player.queue, start=1)
        )
        await interaction.response.send_message(
            "\n".join(lines) if lines else "📭 Hudební fronta je prázdná.",
            ephemeral=True,
        )

    @app_commands.command(name="preskocit", description="Přeskočí právě přehrávanou skladbu.")
    async def skip(self, interaction: discord.Interaction) -> None:
        try:
            voice = await self._require_same_channel(interaction)
        except MusicError as error:
            await interaction.response.send_message(f"❌ {error}", ephemeral=True)
            return

        if not voice.is_playing() and not voice.is_paused():
            await interaction.response.send_message("📭 Teď se nic nepřehrává.", ephemeral=True)
            return
        voice.stop()
        await interaction.response.send_message("⏭️ Skladba byla přeskočena.")

    @app_commands.command(name="pauza", description="Pozastaví právě přehrávanou skladbu.")
    async def pause(self, interaction: discord.Interaction) -> None:
        try:
            voice = await self._require_same_channel(interaction)
        except MusicError as error:
            await interaction.response.send_message(f"❌ {error}", ephemeral=True)
            return

        if not voice.is_playing():
            await interaction.response.send_message("📭 Teď se nic nepřehrává.", ephemeral=True)
            return
        voice.pause()
        await interaction.response.send_message("⏸️ Hudba je pozastavená.")

    @app_commands.command(name="pokracovat", description="Obnoví pozastavenou skladbu.")
    async def resume(self, interaction: discord.Interaction) -> None:
        try:
            voice = await self._require_same_channel(interaction)
        except MusicError as error:
            await interaction.response.send_message(f"❌ {error}", ephemeral=True)
            return

        if not voice.is_paused():
            await interaction.response.send_message("📭 Hudba není pozastavená.", ephemeral=True)
            return
        voice.resume()
        await interaction.response.send_message("▶️ Hudba pokračuje.")

    @app_commands.command(name="zastavit", description="Vyčistí frontu a odpojí bota z voice kanálu.")
    async def stop(self, interaction: discord.Interaction) -> None:
        try:
            voice = await self._require_same_channel(interaction)
        except MusicError as error:
            await interaction.response.send_message(f"❌ {error}", ephemeral=True)
            return

        player = self._player(interaction.guild.id)  # interaction.guild je ověřená výše
        async with player.lock:
            player.queue.clear()
            task = player.task
            player.task = None

        if task and not task.done():
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        voice.stop()
        if voice.is_connected():
            await voice.disconnect()
        await interaction.response.send_message("⏹️ Přehrávání bylo ukončeno a fronta vyčištěna.")

    async def cog_app_command_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        logger.exception("Hudební příkaz selhal: %s", error)
        message = "❌ Hudební příkaz selhal. Zkus to prosím znovu."
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Music(bot))
