import re
from dataclasses import dataclass
from html import unescape
from urllib.parse import urlparse

import feedparser
import aiohttp

from config import YOUTUBE_RSS_URL


@dataclass
class YouTubeChannel:
    channel_id: str
    name: str
    url: str


@dataclass
class YouTubeVideo:
    video_id: str
    title: str
    url: str
    published: str
    channel_name: str
    channel_id: str
    thumbnail: str
    is_live: bool


def _rss_url(channel_id: str) -> str:
    return YOUTUBE_RSS_URL.format(channel_id=channel_id)


def get_latest_video(channel_id: str) -> YouTubeVideo | None:
    feed = feedparser.parse(_rss_url(channel_id))
    if not feed.entries:
        return None

    entry = feed.entries[0]
    video_id = getattr(entry, "yt_videoid", None)
    if not video_id:
        return None

    title = getattr(entry, "title", "Nové YouTube video")
    channel_name = getattr(feed.feed, "title", "YouTube")
    published = getattr(entry, "published", "")
    url = f"https://youtu.be/{video_id}"
    thumbnail = f"https://i.ytimg.com/vi/{video_id}/maxresdefault.jpg"
    text = f"{title} {getattr(entry, 'summary', '')}".upper()
    is_live = "LIVE" in text or "STREAM" in text or "ŽIVĚ" in text

    return YouTubeVideo(
        video_id=video_id,
        title=title,
        url=url,
        published=published,
        channel_name=channel_name,
        channel_id=channel_id,
        thumbnail=thumbnail,
        is_live=is_live,
    )


def get_channel_from_rss(channel_id: str) -> YouTubeChannel | None:
    feed = feedparser.parse(_rss_url(channel_id))
    title = getattr(feed.feed, "title", None)
    if not title:
        return None
    return YouTubeChannel(
        channel_id=channel_id,
        name=title,
        url=f"https://www.youtube.com/channel/{channel_id}",
    )


def _extract_channel_id_from_text(text: str) -> str | None:
    match = re.search(r"channelId\"\s*:\s*\"(UC[\w-]{20,})\"", text)
    if match:
        return match.group(1)
    match = re.search(r"\"externalId\"\s*:\s*\"(UC[\w-]{20,})\"", text)
    if match:
        return match.group(1)
    match = re.search(r"https://www\.youtube\.com/channel/(UC[\w-]{20,})", text)
    if match:
        return match.group(1)
    return None


async def resolve_channel(url_or_id: str) -> YouTubeChannel:
    raw = url_or_id.strip()

    if re.fullmatch(r"UC[\w-]{20,}", raw):
        channel = get_channel_from_rss(raw)
        if channel:
            return channel
        return YouTubeChannel(raw, raw, f"https://www.youtube.com/channel/{raw}")

    parsed = urlparse(raw if raw.startswith("http") else f"https://{raw}")
    path = parsed.path.strip("/")

    if path.startswith("channel/UC"):
        channel_id = path.split("/", 1)[1]
        channel = get_channel_from_rss(channel_id)
        if channel:
            return channel
        return YouTubeChannel(channel_id, channel_id, f"https://www.youtube.com/channel/{channel_id}")

    async with aiohttp.ClientSession() as session:
        async with session.get(raw, timeout=15, headers={"User-Agent": "Mozilla/5.0"}) as resp:
            if resp.status >= 400:
                raise ValueError("YouTube odkaz se nepodařilo načíst.")
            html = await resp.text()

    channel_id = _extract_channel_id_from_text(html)
    if not channel_id:
        raise ValueError("Nepodařilo se zjistit Channel ID z odkazu. Zkus použít odkaz /channel/UC...")

    title_match = re.search(r"<title>(.*?)</title>", html, re.S)
    title = unescape(title_match.group(1)).replace(" - YouTube", "").strip() if title_match else channel_id

    channel = get_channel_from_rss(channel_id)
    if channel:
        return channel
    return YouTubeChannel(channel_id, title, f"https://www.youtube.com/channel/{channel_id}")
