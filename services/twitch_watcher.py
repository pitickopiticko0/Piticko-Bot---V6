import asyncio
import os
from datetime import datetime
from typing import Optional

import discord
from discord.ext import commands, tasks

from utils.logger import logger
from utils.twitch_api import TwitchAPIError, TwitchStream, twitch_api
from utils.twitch_store import twitch_store


def build_twitch_embed(stream: TwitchStream, profile_image_url: Optional[str] = None) -> discord.Embed:
    embed = discord.Embed(
        title=f"🔴 {stream.user_name} právě vysílá na Twitchi!",
        description=f"## {stream.title}",
        url=stream.url,
        color=discord.Color.from_rgb(145, 70, 255),
    )
    embed.add_field(name="🎮 Kategorie", value=stream.game_name, inline=True)
    embed.add_field(name="👥 Diváci", value=f"{stream.viewer_count:,}".replace(",", " "), inline=True)
    if stream.started_at:
        try:
            started = datetime.fromisoformat(stream.started_at.replace("Z", "+00:00"))
            embed.add_field(name="🕒 Začátek", value=f"<t:{int(started.timestamp())}:R>", inline=True)
        except ValueError:
            pass
    if profile_image_url:
        embed.set_author(name=stream.user_name, url=stream.url, icon_url=profile_image_url)
    if stream.thumbnail_url:
        embed.set_image(url=stream.thumbnail_url)
    embed.set_footer(text="Piticko Bot • Twitch oznámení")
    return embed


class TwitchWatcher:
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.interval_minutes = max(1, int(os.getenv("TWITCH_CHECK_INTERVAL_MINUTES", "5")))
        self._lock = asyncio.Lock()
        self.loop.change_interval(minutes=self.interval_minutes)

    def start(self) -> None:
        if not self.loop.is_running():
            self.loop.start()

    def stop(self) -> None:
        self.loop.cancel()

    @tasks.loop(minutes=5)
    async def loop(self) -> None:
        await self.check_all()

    @loop.before_loop
    async def before_loop(self) -> None:
        await self.bot.wait_until_ready()

    @loop.error
    async def loop_error(self, error: Exception) -> None:
        logger.exception("Twitch watcher selhal: %s", error)

    async def check_all(self) -> tuple[int, int]:
        if self._lock.locked():
            return 0, 0
        async with self._lock:
            rows = await asyncio.to_thread(twitch_store.get_enabled_subscriptions)
            if not rows:
                return 0, 0
            logins = sorted({str(row["streamer_login"]).lower() for row in rows})
            try:
                streams = await twitch_api.get_streams(logins)
            except TwitchAPIError:
                logger.exception("Nepodařilo se načíst Twitch streamy.")
                return 0, 0

            found = sent = 0
            for row in rows:
                login = str(row["streamer_login"]).lower()
                stream = streams.get(login)
                guild_id = int(row["guild_id"])
                user_id = str(row["twitch_user_id"])
                last_stream_id = row["last_stream_id"]
                was_live = bool(row["is_live"])

                if stream is None:
                    if was_live:
                        await asyncio.to_thread(
                            twitch_store.set_stream_state, guild_id, user_id, last_stream_id, False
                        )
                    continue

                if str(last_stream_id or "") == stream.id:
                    if not was_live:
                        await asyncio.to_thread(
                            twitch_store.set_stream_state, guild_id, user_id, stream.id, True
                        )
                    continue

                found += 1
                if await self._send_announcement(row, stream):
                    sent += 1
                    await asyncio.to_thread(
                        twitch_store.set_stream_state, guild_id, user_id, stream.id, True
                    )
            return found, sent

    async def _send_announcement(self, row, stream: TwitchStream) -> bool:
        channel_id = int(row["discord_channel_id"])
        channel = self.bot.get_channel(channel_id)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(channel_id)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                logger.warning("Twitch kanál %s nebyl dostupný.", channel_id)
                return False
        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            return False
        role_id = row["mention_role_id"]
        try:
            await channel.send(
                content=f"<@&{role_id}>" if role_id else None,
                embed=build_twitch_embed(stream, row["profile_image_url"]),
                allowed_mentions=discord.AllowedMentions(roles=True, users=False, everyone=False),
            )
            return True
        except discord.HTTPException:
            logger.exception("Odeslání Twitch oznámení do %s selhalo.", channel_id)
            return False
