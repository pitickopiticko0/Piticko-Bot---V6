import discord

from config import BOT_NAME, EMBED_COLOR, EMBED_FOOTER, VERSION
from utils.youtube import YouTubeVideo


def video_embed(video: YouTubeVideo) -> discord.Embed:
    title = f"🔴 LIVE: {video.title}" if video.is_live else f"📺 {video.title}"
    embed = discord.Embed(
        title=title,
        url=video.url,
        description=f"Nový obsah na kanálu **{video.channel_name}**",
        color=EMBED_COLOR,
    )
    embed.set_image(url=video.thumbnail)
    embed.add_field(name="Kanál", value=video.channel_name, inline=True)
    embed.add_field(name="Publikováno", value=video.published or "Neznámé", inline=True)
    embed.set_footer(text=EMBED_FOOTER)
    return embed


def youtube_view(url: str) -> discord.ui.View:
    view = discord.ui.View()
    view.add_item(discord.ui.Button(label="▶ Otevřít na YouTube", url=url))
    return view


def status_embed(bot: discord.Client) -> discord.Embed:
    embed = discord.Embed(title=f"🤖 {BOT_NAME}", color=EMBED_COLOR)
    embed.add_field(name="Stav", value="Online", inline=True)
    embed.add_field(name="Ping", value=f"{round(bot.latency * 1000)} ms", inline=True)
    embed.add_field(name="Verze", value=VERSION, inline=True)
    embed.add_field(name="Servery", value=str(len(bot.guilds)), inline=True)
    return embed
