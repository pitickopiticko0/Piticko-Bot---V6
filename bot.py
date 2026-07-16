import asyncio
import os
from pathlib import Path

import discord
from discord.ext import commands
from dotenv import load_dotenv

from config import GUILD_ID
from services.youtube_watcher import YouTubeWatcher
from utils.logger import logger


load_dotenv()
TOKEN = os.getenv("TOKEN")

if not TOKEN:
    raise RuntimeError(
        "TOKEN není nastavený. Vytvoř .env a vlož TOKEN=tvuj_discord_bot_token"
    )

Path("data").mkdir(exist_ok=True)
Path("logs").mkdir(exist_ok=True)

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents,
    help_command=None,
)


async def load_cogs() -> None:
    loaded = 0

    for file in sorted(os.listdir("cogs")):
        if not file.endswith(".py") or file.startswith("_"):
            continue

        ext = f"cogs.{file[:-3]}"

        try:
            await bot.load_extension(ext)
            logger.info("Načten cog: %s", ext)
            loaded += 1
        except Exception:
            logger.exception("Nepodařilo se načíst cog: %s", ext)

    logger.info("Celkem načteno cogů: %s", loaded)


@bot.event
async def setup_hook() -> None:
    await load_cogs()

    watcher = YouTubeWatcher(bot)
    watcher.start()

    try:
        if GUILD_ID:
            guild = discord.Object(id=GUILD_ID)
            bot.tree.copy_global_to(guild=guild)
            synced = await bot.tree.sync(guild=guild)

            logger.info(
                "Synchronizováno %s slash příkazů pro server %s",
                len(synced),
                GUILD_ID,
            )
        else:
            synced = await bot.tree.sync()

            logger.info(
                "Synchronizováno %s globálních slash příkazů",
                len(synced),
            )

    except Exception:
        logger.exception("Synchronizace slash příkazů selhala")


@bot.event
async def on_ready() -> None:
    logger.info("----------------------------------------")
    logger.info("Bot spuštěn jako %s", bot.user)
    logger.info("ID bota: %s", bot.user.id if bot.user else "neznámé")
    logger.info("Servery: %s", len(bot.guilds))
    logger.info("Members intent: %s", bot.intents.members)
    logger.info("Message content intent: %s", bot.intents.message_content)
    logger.info("----------------------------------------")


@bot.event
async def on_member_join(member: discord.Member):
    logger.info(
        "✅ TEST JOIN -> %s (%s) se připojil na %s (%s)",
        member.name,
        member.id,
        member.guild.name,
        member.guild.id,
    )


@bot.tree.error
async def on_app_command_error(
    interaction: discord.Interaction,
    error: discord.app_commands.AppCommandError,
) -> None:
    original = getattr(error, "original", error)

    if isinstance(original, discord.NotFound):
        logger.warning(
            "Discord interakce %s vypršela nebo už není dostupná.",
            interaction.id,
        )
        return

    logger.exception("Chyba ve slash příkazu: %s", error)

    message = "❌ Nastala chyba při zpracování příkazu."

    try:
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

    except discord.NotFound:
        logger.warning(
            "Na Discord interakci %s už nebylo možné odpovědět.",
            interaction.id,
        )

    except discord.HTTPException as response_error:
        logger.warning(
            "Discord odmítl odpověď na interakci %s: %s",
            interaction.id,
            response_error,
        )


async def main() -> None:
    async with bot:
        await bot.start(TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
