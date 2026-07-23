import asyncio
import os
import time
from dataclasses import dataclass
from typing import Optional

import aiohttp
from dotenv import load_dotenv

load_dotenv()


class KickAPIError(Exception):
    pass


@dataclass(slots=True)
class KickChannel:
    user_id: str
    slug: str
    name: str
    url: str
    profile_image_url: Optional[str]
    live: bool
    title: str
    category: str
    viewer_count: int
    thumbnail_url: Optional[str]


class KickAPI:
    TOKEN_URL = "https://id.kick.com/oauth/token"
    API_URL = "https://api.kick.com/public/v1"

    def __init__(self) -> None:
        self.client_id = os.getenv("KICK_CLIENT_ID")
        self.client_secret = os.getenv("KICK_CLIENT_SECRET")
        self._token: Optional[str] = None
        self._expires_at = 0.0
        self._lock = asyncio.Lock()

    @staticmethod
    def normalize_slug(value: str) -> str:
        value = value.strip()
        for prefix in (
            "https://www.kick.com/", "https://kick.com/", "http://www.kick.com/",
            "http://kick.com/", "www.kick.com/", "kick.com/",
        ):
            if value.lower().startswith(prefix):
                value = value[len(prefix):]
                break
        return value.split("?", 1)[0].split("/", 1)[0].strip().lower()

    async def _get_token(self, force_refresh: bool = False) -> str:
        if not self.client_id or not self.client_secret:
            raise KickAPIError("Chybí KICK_CLIENT_ID nebo KICK_CLIENT_SECRET.")
        if not force_refresh and self._token and time.monotonic() < self._expires_at:
            return self._token
        async with self._lock:
            if not force_refresh and self._token and time.monotonic() < self._expires_at:
                return self._token
            timeout = aiohttp.ClientTimeout(total=20)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(self.TOKEN_URL, data={
                    "grant_type": "client_credentials",
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                }) as response:
                    data = await response.json(content_type=None)
                    if response.status != 200:
                        raise KickAPIError(f"Kick OAuth chyba {response.status}.")
            self._token = data.get("access_token")
            if not self._token:
                raise KickAPIError("Kick nevrátil access token.")
            self._expires_at = time.monotonic() + max(60, int(data.get("expires_in", 3600)) - 120)
            return self._token

    async def _get_channels(self, slug: str, retry_auth: bool = True) -> dict:
        token = await self._get_token()
        timeout = aiohttp.ClientTimeout(total=20)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(
                f"{self.API_URL}/channels",
                params={"slug": slug},
                headers={"Authorization": f"Bearer {token}"},
            ) as response:
                data = await response.json(content_type=None)
                if response.status == 401 and retry_auth:
                    await self._get_token(force_refresh=True)
                    return await self._get_channels(slug, retry_auth=False)
                if response.status != 200:
                    raise KickAPIError(f"Kick API chyba {response.status}.")
                return data

    async def get_channel(self, slug_or_url: str) -> Optional[KickChannel]:
        slug = self.normalize_slug(slug_or_url)
        if not slug:
            return None
        try:
            data = await self._get_channels(slug)
        except (aiohttp.ClientError, asyncio.TimeoutError) as error:
            raise KickAPIError(f"Kick API je nedostupné: {error}") from error
        items = data.get("data", [])
        if not items:
            return None
        item = items[0]
        stream = item.get("stream") or {}
        category = item.get("category") or {}
        return KickChannel(
            user_id=str(item.get("broadcaster_user_id") or item.get("id") or slug),
            slug=str(item.get("slug") or slug),
            name=str(item.get("slug") or slug),
            url=f"https://kick.com/{slug}",
            profile_image_url=item.get("banner_picture"),
            live=bool(stream.get("is_live")),
            title=str(item.get("stream_title") or stream.get("title") or "Kick stream"),
            category=str(category.get("name") or "Bez kategorie"),
            viewer_count=int(stream.get("viewer_count") or 0),
            thumbnail_url=stream.get("thumbnail"),
        )


kick_api = KickAPI()
