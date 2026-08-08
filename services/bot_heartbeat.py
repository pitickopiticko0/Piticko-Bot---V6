import asyncio
import json
import time

import discord
from discord.ext import tasks

from utils.logger import logger
from utils.service_health import mark_success


class BotHeartbeat:
    """Pravidelně zapisuje živý stav Discord bota do sdílené databáze."""

    def __init__(self, bot: discord.Client):
        self.bot = bot
        self.started_at = time.time()

    def start(self) -> None:
        if not self.update.is_running():
            self.update.start()

    @tasks.loop(seconds=60)
    async def update(self) -> None:
        payload = {
            "latency_ms": max(0, round(self.bot.latency * 1000)),
            "uptime_seconds": max(0, int(time.time() - self.started_at)),
            "guild_count": len(self.bot.guilds),
            "user": str(self.bot.user) if self.bot.user else "Neznámý bot",
        }
        await asyncio.to_thread(
            mark_success,
            "discord_bot",
            json.dumps(payload, ensure_ascii=False),
        )

    @update.before_loop
    async def before_update(self) -> None:
        await self.bot.wait_until_ready()

    @update.error
    async def update_error(self, error: BaseException) -> None:
        logger.warning("Heartbeat bota se nepodařilo uložit: %s", error)
