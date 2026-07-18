import asyncio
import os
import time
from dataclasses import dataclass
from typing import Iterable, Optional

import aiohttp
from dotenv import load_dotenv

load_dotenv()


class TwitchAPIError(Exception):
    pass


@dataclass(slots=True)
class TwitchUser:
    id: str
    login: str
    display_name: str
    profile_image_url: Optional[str]
    url: str


@dataclass(slots=True)
class TwitchStream:
    id: str
    user_id: str
    user_login: str
    user_name: str
    title: str
    game_name: str
    viewer_count: int
    started_at: Optional[str]
    thumbnail_url: Optional[str]
    url: str


class TwitchAPI:
    TOKEN_URL = "https://id.twitch.tv/oauth2/token"
    API_URL = "https://api.twitch.tv/helix"

    def __init__(self, client_id: Optional[str] = None, client_secret: Optional[str] = None) -> None:
        self.client_id = client_id or os.getenv("TWITCH_CLIENT_ID")
        self.client_secret = client_secret or os.getenv("TWITCH_CLIENT_SECRET")
        if not self.client_id or not self.client_secret:
            raise TwitchAPIError("Chybí TWITCH_CLIENT_ID nebo TWITCH_CLIENT_SECRET v .env.")
        self._access_token: Optional[str] = None
        self._token_expires_at = 0.0
        self._token_lock = asyncio.Lock()

    async def _get_token(self, force_refresh: bool = False) -> str:
        if not force_refresh and self._access_token and time.monotonic() < self._token_expires_at:
            return self._access_token
        async with self._token_lock:
            if not force_refresh and self._access_token and time.monotonic() < self._token_expires_at:
                return self._access_token
            timeout = aiohttp.ClientTimeout(total=20)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(self.TOKEN_URL, data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "grant_type": "client_credentials",
                }) as response:
                    data = await response.json(content_type=None)
                    if response.status != 200:
                        raise TwitchAPIError(f"Twitch OAuth chyba {response.status}: {data.get('message', 'neznámá chyba')}")
            token = data.get("access_token")
            if not token:
                raise TwitchAPIError("Twitch nevrátil access token.")
            expires_in = int(data.get("expires_in", 3600))
            self._access_token = token
            self._token_expires_at = time.monotonic() + max(60, expires_in - 120)
            return token

    async def _get(self, endpoint: str, params=None, retry_auth: bool = True) -> dict:
        token = await self._get_token()
        headers = {"Client-Id": self.client_id, "Authorization": f"Bearer {token}"}
        timeout = aiohttp.ClientTimeout(total=20)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(f"{self.API_URL}/{endpoint}", headers=headers, params=params) as response:
                data = await response.json(content_type=None)
                if response.status == 401 and retry_auth:
                    await self._get_token(force_refresh=True)
                    return await self._get(endpoint, params, retry_auth=False)
                if response.status != 200:
                    raise TwitchAPIError(f"Twitch API chyba {response.status}: {data.get('message', 'neznámá chyba')}")
                return data

    @staticmethod
    def normalize_login(value: str) -> str:
        value = value.strip()
        for prefix in (
            "https://www.twitch.tv/", "https://twitch.tv/", "http://www.twitch.tv/",
            "http://twitch.tv/", "www.twitch.tv/", "twitch.tv/",
        ):
            if value.lower().startswith(prefix):
                value = value[len(prefix):]
                break
        return value.split("?", 1)[0].split("/", 1)[0].strip().lower()

    async def get_user(self, login_or_url: str) -> Optional[TwitchUser]:
        login = self.normalize_login(login_or_url)
        if not login:
            return None
        data = await self._get("users", {"login": login})
        items = data.get("data", [])
        if not items:
            return None
        item = items[0]
        return TwitchUser(
            id=item["id"], login=item["login"],
            display_name=item.get("display_name") or item["login"],
            profile_image_url=item.get("profile_image_url"),
            url=f"https://www.twitch.tv/{item['login']}",
        )

    async def get_stream(self, login_or_url: str) -> Optional[TwitchStream]:
        login = self.normalize_login(login_or_url)
        return (await self.get_streams([login])).get(login) if login else None

    async def get_streams(self, logins: Iterable[str]) -> dict[str, TwitchStream]:
        normalized = list(dict.fromkeys(login for value in logins if (login := self.normalize_login(value))))
        result: dict[str, TwitchStream] = {}
        for start in range(0, len(normalized), 100):
            chunk = normalized[start:start + 100]
            data = await self._get("streams", [("user_login", login) for login in chunk])
            for item in data.get("data", []):
                login = item["user_login"].lower()
                thumbnail = item.get("thumbnail_url")
                if thumbnail:
                    thumbnail = thumbnail.replace("{width}", "1280").replace("{height}", "720")
                    thumbnail += ("&" if "?" in thumbnail else "?") + f"t={int(time.time())}"
                result[login] = TwitchStream(
                    id=item["id"], user_id=item["user_id"], user_login=login,
                    user_name=item.get("user_name") or login,
                    title=item.get("title") or "Bez názvu",
                    game_name=item.get("game_name") or "Bez kategorie",
                    viewer_count=int(item.get("viewer_count", 0)),
                    started_at=item.get("started_at"), thumbnail_url=thumbnail,
                    url=f"https://www.twitch.tv/{login}",
                )
        return result


twitch_api = TwitchAPI()
