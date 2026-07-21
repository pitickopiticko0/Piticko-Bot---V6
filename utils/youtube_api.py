import asyncio
import re
from dataclasses import dataclass
from typing import Optional

import aiohttp

from config import YOUTUBE_API_KEY


class YouTubeAPIError(Exception):
    pass


@dataclass
class YouTubeChannel:
    id: str
    title: str
    url: str
    thumbnail: Optional[str]
    uploads_playlist_id: Optional[str]


@dataclass
class YouTubeVideo:
    id: str
    title: str
    url: str
    thumbnail: Optional[str]
    published_at: Optional[str]
    live: bool = False


class YouTubeAPI:
    BASE_URL = "https://www.googleapis.com/youtube/v3"
    MAX_ATTEMPTS = 3
    RETRY_DELAYS = (1, 2)

    def __init__(self, api_key: Optional[str] = YOUTUBE_API_KEY):
        if not api_key:
            raise YouTubeAPIError("Chybí YOUTUBE_API_KEY v .env")
        self.api_key = api_key

    async def _get(self, endpoint: str, params: dict) -> dict:
        request_params = {**params, "key": self.api_key}
        timeout = aiohttp.ClientTimeout(total=20)

        for attempt in range(self.MAX_ATTEMPTS):
            try:
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get(
                        f"{self.BASE_URL}/{endpoint}",
                        params=request_params,
                    ) as response:
                        data = await response.json(content_type=None)

                        if response.status == 200:
                            return data

                        message = data.get("error", {}).get(
                            "message",
                            "Neznámá chyba YouTube API",
                        )

                        # Rate limit a chyby serveru mohou být jen dočasné.
                        if response.status != 429 and response.status < 500:
                            raise YouTubeAPIError(message)

                        if attempt == self.MAX_ATTEMPTS - 1:
                            raise YouTubeAPIError(message)

            except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                if attempt == self.MAX_ATTEMPTS - 1:
                    raise YouTubeAPIError(
                        "YouTube API je dočasně nedostupné kvůli "
                        f"síťové chybě: {exc}"
                    ) from exc

            await asyncio.sleep(self.RETRY_DELAYS[attempt])

        raise YouTubeAPIError("YouTube API je dočasně nedostupné.")

    def _extract_handle(self, url: str) -> Optional[str]:
        match = re.search(r"youtube\.com/@([^/?]+)", url)
        return match.group(1) if match else None

    def _extract_channel_id(self, url: str) -> Optional[str]:
        match = re.search(r"youtube\.com/channel/([^/?]+)", url)
        return match.group(1) if match else None

    async def resolve_channel(self, url: str) -> YouTubeChannel:
        channel_id = self._extract_channel_id(url)

        if channel_id:
            return await self.get_channel(channel_id)

        handle = self._extract_handle(url)

        if handle:
            return await self.get_channel_by_handle(handle)

        raise YouTubeAPIError("Nepodporovaný YouTube odkaz. Použij /@handle nebo /channel/ID.")

    async def get_channel_by_handle(self, handle: str) -> YouTubeChannel:
        data = await self._get(
            "channels",
            {
                "part": "snippet,contentDetails",
                "forHandle": handle,
                "maxResults": 1,
            },
        )

        items = data.get("items", [])

        if not items:
            raise YouTubeAPIError("YouTube kanál nebyl nalezen.")

        return self._parse_channel(items[0])

    async def get_channel(self, channel_id: str) -> YouTubeChannel:
        data = await self._get(
            "channels",
            {
                "part": "snippet,contentDetails",
                "id": channel_id,
                "maxResults": 1,
            },
        )

        items = data.get("items", [])

        if not items:
            raise YouTubeAPIError("YouTube kanál nebyl nalezen.")

        return self._parse_channel(items[0])

    def _parse_channel(self, item: dict) -> YouTubeChannel:
        snippet = item.get("snippet", {})
        thumbnails = snippet.get("thumbnails", {})
        content = item.get("contentDetails", {})

        return YouTubeChannel(
            id=item["id"],
            title=snippet.get("title", "Neznámý kanál"),
            url=f"https://www.youtube.com/channel/{item['id']}",
            thumbnail=(
                thumbnails.get("high", {})
                or thumbnails.get("medium", {})
                or thumbnails.get("default", {})
            ).get("url"),
            uploads_playlist_id=content.get("relatedPlaylists", {}).get("uploads"),
        )

    async def get_latest_video(self, channel_id: str) -> Optional[YouTubeVideo]:
        channel = await self.get_channel(channel_id)

        if not channel.uploads_playlist_id:
            return None

        data = await self._get(
            "playlistItems",
            {
                "part": "snippet",
                "playlistId": channel.uploads_playlist_id,
                "maxResults": 1,
            },
        )

        items = data.get("items", [])

        if not items:
            return None

        snippet = items[0].get("snippet", {})
        resource = snippet.get("resourceId", {})
        video_id = resource.get("videoId")

        if not video_id:
            return None

        video_data = await self._get(
            "videos",
            {
                "part": "snippet,liveStreamingDetails",
                "id": video_id,
            },
        )

        live = False
        if video_data.get("items"):
            live_snippet = video_data["items"][0].get("snippet", {})
            live = live_snippet.get("liveBroadcastContent") == "live"

        thumbnails = snippet.get("thumbnails", {})

        return YouTubeVideo(
            id=video_id,
            title=snippet.get("title", "Bez názvu"),
            url=f"https://www.youtube.com/watch?v={video_id}",
            thumbnail=(
                thumbnails.get("maxres", {})
                or thumbnails.get("high", {})
                or thumbnails.get("medium", {})
                or thumbnails.get("default", {})
            ).get("url"),
            published_at=snippet.get("publishedAt"),
            live=live,
        )


youtube_api = YouTubeAPI()
