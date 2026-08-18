import asyncio
import json
from pathlib import Path
import subprocess
import time

import discord
from discord.ext import tasks
import psutil

from config import VERSION
from utils.logger import logger
from utils.service_health import mark_success


PROJECT_DIR = Path(__file__).resolve().parent.parent


def _git_revision() -> str | None:
    """Vrátí krátký hash nasazené revize bez síťového požadavku."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=PROJECT_DIR,
            capture_output=True,
            check=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() or None


class BotHeartbeat:
    """Pravidelně zapisuje živý stav Discord bota do sdílené databáze."""

    def __init__(self, bot: discord.Client):
        self.bot = bot
        self.started_at = time.time()
        self.process = psutil.Process()
        self.revision = _git_revision()
        psutil.cpu_percent(interval=None)

    def start(self) -> None:
        if not self.update.is_running():
            self.update.start()

    @tasks.loop(seconds=60)
    async def update(self) -> None:
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage(str(PROJECT_DIR))
        payload = {
            "latency_ms": max(0, round(self.bot.latency * 1000)),
            "uptime_seconds": max(0, int(time.time() - self.started_at)),
            "guild_count": len(self.bot.guilds),
            "user": str(self.bot.user) if self.bot.user else "Neznámý bot",
            "version": VERSION,
            "revision": self.revision,
            "cpu_percent": round(psutil.cpu_percent(interval=None), 1),
            "memory_percent": round(memory.percent, 1),
            "memory_used_mb": round(memory.used / 1024 / 1024),
            "memory_total_mb": round(memory.total / 1024 / 1024),
            "process_memory_mb": round(self.process.memory_info().rss / 1024 / 1024),
            "disk_percent": round(disk.percent, 1),
            "disk_free_gb": round(disk.free / 1024 / 1024 / 1024, 1),
            "disk_total_gb": round(disk.total / 1024 / 1024 / 1024, 1),
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
