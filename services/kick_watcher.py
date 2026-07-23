import asyncio
import os

import discord
from discord.ext import commands, tasks

from utils.kick_api import KickAPIError, kick_api
from utils import kick_store
from utils.logger import logger
from utils.service_health import mark_error, mark_success


class KickWatcher:
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._lock = asyncio.Lock()
        self.loop.change_interval(minutes=max(1, int(os.getenv("KICK_CHECK_INTERVAL_MINUTES", "5"))))

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
        mark_error("kick", error)
        logger.exception("Kick watcher selhal: %s", error)

    async def check_all(self) -> tuple[int, int]:
        if self._lock.locked():
            return 0, 0
        async with self._lock:
            rows = await asyncio.to_thread(kick_store.get_enabled)
            if not rows:
                mark_success("kick", "Žádné aktivní odběry.")
                return 0, 0
            found = sent = errors = 0
            for row in rows:
                try:
                    channel = await kick_api.get_channel(row["streamer_slug"])
                    if channel is None:
                        continue
                    was_live = bool(row["is_live"])
                    if not channel.live:
                        if was_live:
                            await asyncio.to_thread(
                                kick_store.set_live, int(row["guild_id"]),
                                str(row["kick_user_id"]), False,
                            )
                        continue
                    if was_live:
                        continue
                    found += 1
                    channel_id = int(row["discord_channel_id"])
                    target = self.bot.get_channel(channel_id)
                    if target is None:
                        try:
                            target = await self.bot.fetch_channel(channel_id)
                        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                            logger.warning("Kick kanál %s nebyl dostupný.", channel_id)
                            continue
                    if not isinstance(target, (discord.TextChannel, discord.Thread)):
                        continue
                    role_id = row["mention_role_id"]
                    embed = discord.Embed(
                        title=f"🟢 {channel.name} právě vysílá na Kicku!",
                        description=f"## {channel.title}",
                        url=channel.url,
                        color=discord.Color.from_rgb(83, 252, 24),
                    )
                    embed.add_field(name="Kategorie", value=channel.category, inline=True)
                    embed.add_field(name="Diváci", value=str(channel.viewer_count), inline=True)
                    if channel.thumbnail_url:
                        embed.set_image(url=channel.thumbnail_url)
                    try:
                        await target.send(
                            content=f"<@&{role_id}>" if role_id else None,
                            embed=embed,
                            allowed_mentions=discord.AllowedMentions(
                                roles=True, users=False, everyone=False
                            ),
                        )
                    except discord.HTTPException:
                        logger.exception("Odeslání Kick oznámení do %s selhalo.", channel_id)
                        continue
                    await asyncio.to_thread(
                        kick_store.set_live, int(row["guild_id"]),
                        str(row["kick_user_id"]), True,
                    )
                    sent += 1
                except KickAPIError as error:
                    errors += 1
                    mark_error("kick", error)
                    logger.warning("Kick kontrola %s selhala: %s", row["streamer_slug"], error)
            if not errors:
                mark_success("kick", f"Nalezeno: {found}, odesláno: {sent}")
            return found, sent
