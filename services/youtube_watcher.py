import asyncio
from typing import Optional

import discord
from discord.ext import commands

from config import CHECK_INTERVAL, EMBED_COLOR, EMBED_FOOTER
from utils.database import db
from utils.logger import logger
from utils.time_utils import format_discord_time
from utils.views import youtube_video_view
from utils.youtube_api import youtube_api
from utils.youtube_message import render_youtube_message


class YouTubeWatcher:
    """
    Background service that checks all enabled YouTube subscriptions
    and sends Discord notifications for newly published videos.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.task: Optional[asyncio.Task] = None

    def start(self) -> None:
        if self.task is not None and not self.task.done():
            logger.info("YouTube watcher už běží.")
            return

        self.task = asyncio.create_task(self._loop())
        logger.info("YouTube watcher spuštěn.")

    async def _loop(self) -> None:
        await self.bot.wait_until_ready()

        while not self.bot.is_closed():
            try:
                await self.check_all()
            except Exception:
                logger.exception("Neočekávaná chyba v YouTube watcheru.")

            await asyncio.sleep(CHECK_INTERVAL)

    async def check_all(self) -> None:
        subscriptions = db.get_enabled_subscriptions()

        if not subscriptions:
            logger.info("YouTube watcher: žádné aktivní odběry.")
            return

        logger.info("YouTube watcher: kontroluji %s odběrů.", len(subscriptions))

        for sub in subscriptions:
            try:
                await self._check_subscription(sub)
            except Exception:
                logger.exception(
                    "Chyba při kontrole YouTube kanálu %s pro guild %s.",
                    sub["youtube_channel_id"],
                    sub["guild_id"],
                )

    async def _check_subscription(self, sub) -> None:
        latest = await youtube_api.get_latest_video(sub["youtube_channel_id"])

        if latest is None:
            logger.warning(
                "YouTube watcher: kanál %s nevrátil žádné video.",
                sub["youtube_channel_id"],
            )
            return

        if sub["last_video_id"] == latest.id:
            logger.info(
                "YouTube watcher: žádné nové video pro %s.",
                sub["youtube_name"],
            )
            return

        # První kontrola po přidání kanálu:
        # uložíme aktuální poslední video, ale neposíláme staré oznámení.
        if sub["last_video_id"] is None:
            db.add_video(
                video_id=latest.id,
                youtube_channel_id=sub["youtube_channel_id"],
                title=latest.title,
                url=latest.url,
                published_at=latest.published_at,
            )

            db.set_last_video(
                guild_id=sub["guild_id"],
                youtube_channel_id=sub["youtube_channel_id"],
                video_id=latest.id,
            )

            logger.info(
                "YouTube watcher: inicializován kanál %s posledním videem %s.",
                sub["youtube_name"],
                latest.id,
            )
            return

        discord_channel = self.bot.get_channel(sub["discord_channel_id"])

        if discord_channel is None:
            logger.warning(
                "YouTube watcher: Discord kanál %s nebyl nalezen.",
                sub["discord_channel_id"],
            )
            return

        mention = None
        if sub["mention_role_id"]:
            mention = f"<@&{sub['mention_role_id']}>"

        content = render_youtube_message(
            sub["custom_message"],
            title=latest.title,
            url=latest.url,
            channel=sub["youtube_name"],
            channel_url=sub["youtube_url"],
            thumbnail=latest.thumbnail,
            published=format_discord_time(latest.published_at),
            role=mention,
        )

        embed = self._build_video_embed(
            title=latest.title,
            url=latest.url,
            channel_name=sub["youtube_name"],
            thumbnail=latest.thumbnail,
            published_at=latest.published_at,
        )

        await discord_channel.send(
            content=content,
            embed=embed,
            view=youtube_video_view(latest.url),
        )

        db.add_video(
            video_id=latest.id,
            youtube_channel_id=sub["youtube_channel_id"],
            title=latest.title,
            url=latest.url,
            published_at=latest.published_at,
        )

        db.set_last_video(
            guild_id=sub["guild_id"],
            youtube_channel_id=sub["youtube_channel_id"],
            video_id=latest.id,
        )

        logger.info(
            "YouTube watcher: odesláno nové video %s pro %s.",
            latest.id,
            sub["youtube_name"],
        )

    def _build_video_embed(
        self,
        title: str,
        url: str,
        channel_name: str,
        thumbnail: str | None,
        published_at: str | None,
    ) -> discord.Embed:
        embed = discord.Embed(
            title="📺 Nové video",
            description=f"**{title}**",
            url=url,
            color=EMBED_COLOR,
        )

        embed.add_field(
            name="Kanál",
            value=channel_name,
            inline=False,
        )

        published_text = format_discord_time(published_at)

        if published_text:
            embed.add_field(
                name="Publikováno",
                value=published_text,
                inline=False,
            )

        if thumbnail:
            embed.set_image(url=thumbnail)

        embed.set_footer(text=EMBED_FOOTER)
        return embed
