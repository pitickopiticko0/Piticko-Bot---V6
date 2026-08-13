import asyncio
import base64
from datetime import datetime, timezone
import json
import os
import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dotenv import load_dotenv
import aiohttp
import httpx
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from dashboard.auth import router as auth_router
from dashboard.storage import DashboardStorage
from utils import kick_store
from utils.database import db
from utils.kick_api import KickAPIError, kick_api
from utils.twitch_api import TwitchAPIError, twitch_api
from utils.twitch_store import twitch_store
from utils.service_health import get_all as get_service_health
from utils.support import get_support_url


load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
templates.env.globals["support_url"] = get_support_url()
storage = DashboardStorage()

SECRET_KEY = os.getenv("DASHBOARD_SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError("Chybí proměnná DASHBOARD_SECRET_KEY.")

app = FastAPI(
    title="Piticko Dashboard V3",
    version="3.0.0",
)


@app.middleware("http")
async def reject_cross_site_writes(request: Request, call_next):
    """Blokuje cizí zápisy a přidává bezpečnostní hlavičky."""
    response = None
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        fetch_site = request.headers.get("sec-fetch-site", "").lower()
        if fetch_site == "cross-site":
            response = JSONResponse(
                {"detail": "Cross-site požadavek byl odmítnut."},
                status_code=403,
            )

        origin = request.headers.get("origin") if response is None else None
        if response is None and origin:
            origin_host = urlsplit(origin).netloc.lower()
            request_host = request.headers.get("host", "").lower()
            if not origin_host or origin_host != request_host:
                response = JSONResponse(
                    {"detail": "Neplatný původ požadavku."},
                    status_code=403,
                )

    if response is None:
        response = await call_next(request)

    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = (
        "camera=(), microphone=(), geolocation=(), payment=()"
    )
    response.headers["Content-Security-Policy"] = (
        "frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    )
    if not request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-store"

    forwarded_proto = request.headers.get("x-forwarded-proto", "").lower()
    if request.url.scheme == "https" or forwarded_proto == "https":
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains"
        )

    return response

app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET_KEY,
    session_cookie="piticko_dashboard_session",
    same_site="lax",
    https_only=os.getenv("DASHBOARD_HTTPS_ONLY", "true").lower() == "true",
    max_age=60 * 60 * 24 * 7,
)

app.mount(
    "/static",
    StaticFiles(directory=str(BASE_DIR / "static")),
    name="static",
)

app.include_router(auth_router)

STARTED_AT = time.time()
DISCORD_API = "https://discord.com/api/v10"
DISCORD_CDN = "https://cdn.discordapp.com"
MAX_AVATAR_SIZE = 8 * 1024 * 1024
ALLOWED_AVATAR_TYPES = {"image/png", "image/jpeg", "image/webp", "image/gif"}
VIEW_CHANNEL = 1 << 10
SEND_MESSAGES = 1 << 11
ADMINISTRATOR = 1 << 3
MANAGE_ROLES = 1 << 28
DISCORD_RESOURCE_CACHE_TTL = 20.0
DISCORD_RESOURCE_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
DISCORD_RESOURCE_LOCKS: dict[str, asyncio.Lock] = {}


def current_user(request: Request) -> dict[str, Any] | None:
    user = request.session.get("user")
    return user if isinstance(user, dict) else None


def available_guilds(request: Request) -> list[dict[str, Any]]:
    guilds = request.session.get("guilds", [])
    return guilds if isinstance(guilds, list) else []


def require_login(request: Request):
    if not current_user(request):
        return RedirectResponse("/login-page", status_code=303)
    return None


def get_accessible_guild(request: Request, guild_id: str) -> dict[str, Any]:
    for guild in available_guilds(request):
        if str(guild.get("id")) == str(guild_id):
            return guild
    raise HTTPException(status_code=403, detail="K tomuto serveru nemáš přístup.")


def bot_authorization() -> dict[str, str]:
    token = os.getenv("TOKEN", "").strip()
    if not token:
        raise RuntimeError("Chybí proměnná TOKEN pro komunikaci s Discord API.")
    return {"Authorization": f"Bot {token}"}


def valid_avatar_image(content_type: str, content: bytes) -> bool:
    signatures = {
        "image/png": content.startswith(b"\x89PNG\r\n\x1a\n"),
        "image/jpeg": content.startswith(b"\xff\xd8\xff"),
        "image/webp": (
            len(content) >= 12
            and content.startswith(b"RIFF")
            and content[8:12] == b"WEBP"
        ),
        "image/gif": content.startswith((b"GIF87a", b"GIF89a")),
    }
    return signatures.get(content_type, False)


def avatar_url(guild_id: str, member: dict[str, Any]) -> str:
    user = member.get("user") or {}
    user_id = str(user.get("id") or "0")
    guild_avatar = member.get("avatar")

    if guild_avatar:
        extension = "gif" if str(guild_avatar).startswith("a_") else "webp"
        return (
            f"{DISCORD_CDN}/guilds/{guild_id}/users/{user_id}/avatars/"
            f"{guild_avatar}.{extension}?size=256"
        )

    global_avatar = user.get("avatar")
    if global_avatar:
        extension = "gif" if str(global_avatar).startswith("a_") else "webp"
        return f"{DISCORD_CDN}/avatars/{user_id}/{global_avatar}.{extension}?size=256"

    default_index = (int(user_id) >> 22) % 6 if user_id.isdigit() else 0
    return f"{DISCORD_CDN}/embed/avatars/{default_index}.png"


def bot_can_send_to_channel(
    guild_id: str,
    member: dict[str, Any],
    roles: list[dict[str, Any]],
    channel: dict[str, Any],
) -> bool:
    role_permissions = {
        str(role.get("id")): int(role.get("permissions", 0))
        for role in roles
    }
    member_role_ids = {str(role_id) for role_id in member.get("roles", [])}
    permissions = role_permissions.get(str(guild_id), 0)
    for role_id in member_role_ids:
        permissions |= role_permissions.get(role_id, 0)

    if permissions & ADMINISTRATOR:
        return True

    overwrites = channel.get("permission_overwrites") or []

    def apply_overwrite(overwrite: dict[str, Any]) -> None:
        nonlocal permissions
        permissions &= ~int(overwrite.get("deny", 0))
        permissions |= int(overwrite.get("allow", 0))

    everyone = next(
        (item for item in overwrites if str(item.get("id")) == str(guild_id)),
        None,
    )
    if everyone:
        apply_overwrite(everyone)

    role_denies = 0
    role_allows = 0
    for overwrite in overwrites:
        if (
            int(overwrite.get("type", 0)) == 0
            and str(overwrite.get("id")) in member_role_ids
        ):
            role_denies |= int(overwrite.get("deny", 0))
            role_allows |= int(overwrite.get("allow", 0))
    permissions &= ~role_denies
    permissions |= role_allows

    user_id = str((member.get("user") or {}).get("id", ""))
    member_overwrite = next(
        (
            item for item in overwrites
            if int(item.get("type", 0)) == 1
            and str(item.get("id")) == user_id
        ),
        None,
    )
    if member_overwrite:
        apply_overwrite(member_overwrite)

    required = VIEW_CHANNEL | SEND_MESSAGES
    return permissions & required == required


def bot_can_post_to_forum(
    guild_id: str,
    member: dict[str, Any],
    roles: list[dict[str, Any]],
    channel: dict[str, Any],
) -> bool:
    # Discord u forum příspěvků vyžaduje oprávnění Send Messages;
    # Create Public Threads se u thread-only kanálů ignoruje.
    return bot_can_send_to_channel(guild_id, member, roles, channel)


async def discord_get_with_retry(
    client: httpx.AsyncClient,
    url: str,
    headers: dict[str, str],
) -> httpx.Response:
    response = await client.get(url, headers=headers)
    if response.status_code != 429:
        return response

    try:
        retry_after = float(response.json().get("retry_after", 0))
    except (TypeError, ValueError, json.JSONDecodeError):
        try:
            retry_after = float(response.headers.get("Retry-After", 0))
        except (TypeError, ValueError):
            retry_after = 0

    if retry_after <= 0 or retry_after > 10:
        return response

    await asyncio.sleep(retry_after + 0.1)
    return await client.get(url, headers=headers)


async def get_bot_guild_resources(guild_id: str) -> dict[str, Any]:
    empty = {
        "profile": None,
        "channels": [],
        "categories": [],
        "forums": [],
        "roles": [],
        "can_manage_roles": False,
        "available": False,
    }
    cached = DISCORD_RESOURCE_CACHE.get(guild_id)
    if cached and time.monotonic() - cached[0] < DISCORD_RESOURCE_CACHE_TTL:
        return cached[1]

    lock = DISCORD_RESOURCE_LOCKS.setdefault(guild_id, asyncio.Lock())
    async with lock:
        cached = DISCORD_RESOURCE_CACHE.get(guild_id)
        if cached and time.monotonic() - cached[0] < DISCORD_RESOURCE_CACHE_TTL:
            return cached[1]

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                headers = bot_authorization()
                member_response, channels_response, roles_response = await asyncio.gather(
                    discord_get_with_retry(
                        client,
                        f"{DISCORD_API}/guilds/{guild_id}/members/@me",
                        headers,
                    ),
                    discord_get_with_retry(
                        client,
                        f"{DISCORD_API}/guilds/{guild_id}/channels",
                        headers,
                    ),
                    discord_get_with_retry(
                        client,
                        f"{DISCORD_API}/guilds/{guild_id}/roles",
                        headers,
                    ),
                )
        except (httpx.HTTPError, RuntimeError):
            return empty

        if any(
            response.status_code != 200
            for response in (member_response, channels_response, roles_response)
        ):
            return empty

        try:
            member = member_response.json()
            raw_channels = channels_response.json()
            raw_roles = roles_response.json()
        except (TypeError, ValueError, json.JSONDecodeError):
            return empty
        member_role_ids = {
            str(role_id) for role_id in member.get("roles", [])
        }
        base_permissions = next(
            (
                int(role.get("permissions", 0))
                for role in raw_roles
                if str(role.get("id")) == str(guild_id)
            ),
            0,
        )
        for role in raw_roles:
            if str(role.get("id")) in member_role_ids:
                base_permissions |= int(role.get("permissions", 0))
        can_manage_roles = bool(
            base_permissions & (ADMINISTRATOR | MANAGE_ROLES)
        )
        top_role_position = max(
            (
                int(role.get("position", 0))
                for role in raw_roles
                if str(role.get("id")) in member_role_ids
            ),
            default=0,
        )
        channels = [
            {
                "id": str(channel["id"]),
                "name": channel.get("name") or "bez-názvu",
                "can_send": bot_can_send_to_channel(
                    guild_id, member, raw_roles, channel
                ),
            }
            for channel in raw_channels
            if int(channel.get("type", -1)) in (0, 5)
        ]
        channels.sort(key=lambda item: item["name"].casefold())
        categories = [
            {
                "id": str(channel["id"]),
                "name": channel.get("name") or "Kategorie",
            }
            for channel in raw_channels
            if int(channel.get("type", -1)) == 4
        ]
        categories.sort(key=lambda item: item["name"].casefold())
        forums = [
            {
                "id": str(channel["id"]),
                "name": channel.get("name") or "Fórum",
                "can_post": bot_can_post_to_forum(
                    guild_id, member, raw_roles, channel
                ),
            }
            for channel in raw_channels
            if int(channel.get("type", -1)) == 15
        ]
        forums.sort(key=lambda item: item["name"].casefold())
        roles = [
            {
                "id": str(role["id"]),
                "name": role.get("name") or "Role",
                "position": int(role.get("position", 0)),
                "assignable": (
                    can_manage_roles
                    and int(role.get("position", 0)) < top_role_position
                ),
            }
            for role in raw_roles
            if str(role.get("id")) != str(guild_id)
            and not role.get("managed", False)
        ]
        roles.sort(key=lambda item: item["position"], reverse=True)

        result = {
            "profile": {
                "avatar_url": avatar_url(guild_id, member),
                "has_custom_avatar": bool(member.get("avatar")),
            },
            "channels": channels,
            "categories": categories,
            "forums": forums,
            "roles": roles,
            "can_manage_roles": can_manage_roles,
            "available": True,
        }
        DISCORD_RESOURCE_CACHE[guild_id] = (time.monotonic(), result)
        return result


async def set_bot_guild_avatar(guild_id: str, image: str | None) -> None:
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.patch(
            f"{DISCORD_API}/guilds/{guild_id}/members/@me",
            headers=bot_authorization(),
            json={"avatar": image},
        )

    if response.status_code != 200:
        raise RuntimeError(
            f"Discord odmítl změnu avataru (HTTP {response.status_code})."
        )


@app.on_event("startup")
async def startup() -> None:
    await storage.initialize()


@app.get("/health")
async def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "version": "3.0.0",
        "uptime_seconds": int(time.time() - STARTED_AT),
        "storage": storage.backend_name,
    }


def summarize_service_health(rows: list[Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    services = [{key: row[key] for key in row.keys()} for row in rows]
    bot_health = {
        "online": False,
        "last_seen": None,
        "latency_ms": None,
        "uptime_seconds": 0,
        "guild_count": None,
        "user": None,
    }
    watcher_services = []
    for service in services:
        if service["service"] != "discord_bot":
            watcher_services.append(service)
            continue

        bot_health["last_seen"] = service["checked_at"]
        try:
            checked_at = datetime.fromisoformat(str(service["checked_at"]).replace("Z", "+00:00"))
            if checked_at.tzinfo is None:
                checked_at = checked_at.replace(tzinfo=timezone.utc)
            age_seconds = (datetime.now(timezone.utc) - checked_at).total_seconds()
            bot_health["online"] = service["status"] == "ok" and age_seconds <= 150
        except (TypeError, ValueError):
            bot_health["online"] = False

        try:
            details = json.loads(service["message"] or "{}")
            bot_health["latency_ms"] = details.get("latency_ms")
            bot_health["uptime_seconds"] = max(0, int(details.get("uptime_seconds", 0)))
            bot_health["guild_count"] = details.get("guild_count")
            bot_health["user"] = details.get("user")
        except (TypeError, ValueError, json.JSONDecodeError):
            pass

    return bot_health, watcher_services


@app.get("/diagnostics", response_class=HTMLResponse)
async def diagnostics(request: Request):
    redirect = require_login(request)
    if redirect:
        return redirect

    database_ok = True
    database_error = ""
    rows = []
    try:
        rows = await asyncio.to_thread(get_service_health)
    except Exception as error:
        database_ok = False
        database_error = str(error)[:500]

    bot_health, watcher_services = summarize_service_health(rows)
    api_configuration = {
        "Discord bot": bool(os.getenv("TOKEN")),
        "YouTube API": bool(os.getenv("YOUTUBE_API_KEY")),
        "Twitch API": bool(os.getenv("TWITCH_CLIENT_ID") and os.getenv("TWITCH_CLIENT_SECRET")),
        "Kick API": bool(os.getenv("KICK_CLIENT_ID") and os.getenv("KICK_CLIENT_SECRET")),
    }
    return templates.TemplateResponse(
        request=request,
        name="diagnostics.html",
        context={
            "page_title": "Diagnostika",
            "user": current_user(request),
            "database_ok": database_ok,
            "database_error": database_error,
            "services": watcher_services,
            "bot_health": bot_health,
            "api_configuration": api_configuration,
            "uptime_seconds": int(time.time() - STARTED_AT),
        },
    )


@app.get("/login-page", response_class=HTMLResponse)
async def login_page(request: Request):
    if current_user(request):
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={"page_title": "Přihlášení"},
    )


@app.get("/", response_class=HTMLResponse)
async def dashboard_home(request: Request):
    redirect = require_login(request)
    if redirect:
        return redirect

    guilds = available_guilds(request)
    configured = await storage.count_configured_guilds(
        [str(g.get("id")) for g in guilds]
    )
    try:
        health_rows = await asyncio.to_thread(get_service_health)
    except Exception:
        health_rows = []
    bot_health, _ = summarize_service_health(health_rows)

    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "page_title": "Přehled",
            "user": current_user(request),
            "guilds": guilds,
            "configured_count": configured,
            "bot_health": bot_health,
            "uptime_seconds": int(time.time() - STARTED_AT),
        },
    )


@app.get("/server/{guild_id}", response_class=HTMLResponse)
async def server_dashboard(request: Request, guild_id: str):
    redirect = require_login(request)
    if redirect:
        return redirect

    guild = get_accessible_guild(request, guild_id)
    settings = await storage.get_settings(guild_id)
    discord_resources = await get_bot_guild_resources(guild_id)
    twitch_subscriptions = await asyncio.to_thread(
        twitch_store.get_guild_subscriptions, int(guild_id)
    )
    kick_subscriptions = await asyncio.to_thread(kick_store.get_guild, int(guild_id))
    giveaways = await storage.get_giveaways(guild_id)
    makejpc_products = await storage.get_makejpc_products()
    moderation_events = await storage.get_moderation_events(guild_id)
    pc_advice_requests = await asyncio.to_thread(
        db.get_recent_pc_advice, int(guild_id), 20
    )
    abi_rank_requests = await asyncio.to_thread(
        db.get_recent_abi_ranks, int(guild_id), 20
    )

    return templates.TemplateResponse(
        request=request,
        name="server.html",
        context={
            "page_title": guild.get("name", "Server"),
            "user": current_user(request),
            "guild": guild,
            "settings": settings,
            "bot_profile": discord_resources["profile"],
            "discord_channels": discord_resources["channels"],
            "discord_categories": discord_resources["categories"],
            "discord_forums": discord_resources["forums"],
            "discord_roles": discord_resources["roles"],
            "discord_resources_available": discord_resources["available"],
            "twitch_subscriptions": twitch_subscriptions,
            "kick_subscriptions": kick_subscriptions,
            "giveaways": giveaways,
            "makejpc_products": makejpc_products,
            "moderation_events": moderation_events,
            "pc_advice_requests": pc_advice_requests,
            "abi_rank_requests": abi_rank_requests,
        },
    )


@app.post("/server/{guild_id}/twitch/add")
async def add_twitch_subscription(
    request: Request,
    guild_id: str,
    streamer: str = Form(default=""),
    channel_id: str = Form(default=""),
    mention_role_id: str = Form(default=""),
):
    redirect = require_login(request)
    if redirect:
        return redirect
    get_accessible_guild(request, guild_id)

    streamer = streamer.strip()
    if not streamer or not channel_id.isdigit() or (mention_role_id and not mention_role_id.isdigit()):
        return RedirectResponse(f"/server/{guild_id}?twitch_error=invalid#twitch", status_code=303)
    resources = await get_bot_guild_resources(guild_id)
    if resources["available"]:
        allowed_channels = {
            str(channel["id"])
            for channel in resources["channels"]
            if channel.get("can_send")
        }
        allowed_roles = {str(role["id"]) for role in resources["roles"]}
        if channel_id not in allowed_channels or (
            mention_role_id and mention_role_id not in allowed_roles
        ):
            return RedirectResponse(
                f"/server/{guild_id}?twitch_error=invalid#twitch", status_code=303
            )
    try:
        user = await twitch_api.get_user(streamer)
    except (TwitchAPIError, aiohttp.ClientError, asyncio.TimeoutError, OSError):
        return RedirectResponse(f"/server/{guild_id}?twitch_error=api#twitch", status_code=303)
    if user is None:
        return RedirectResponse(f"/server/{guild_id}?twitch_error=not-found#twitch", status_code=303)

    await asyncio.to_thread(
        twitch_store.add_subscription,
        int(guild_id), user.id, user.login, user.display_name,
        int(channel_id), int(mention_role_id) if mention_role_id else None,
        user.profile_image_url,
    )
    return RedirectResponse(f"/server/{guild_id}?saved=twitch#twitch", status_code=303)


@app.post("/server/{guild_id}/twitch/remove")
async def remove_twitch_subscription(
    request: Request,
    guild_id: str,
    streamer_login: str = Form(default=""),
):
    redirect = require_login(request)
    if redirect:
        return redirect
    get_accessible_guild(request, guild_id)
    await asyncio.to_thread(
        twitch_store.remove_subscription, int(guild_id), streamer_login.strip()
    )
    return RedirectResponse(f"/server/{guild_id}?saved=twitch-remove#twitch", status_code=303)


@app.post("/server/{guild_id}/kick/add")
async def add_kick_subscription(
    request: Request,
    guild_id: str,
    streamer: str = Form(default=""),
    channel_id: str = Form(default=""),
    mention_role_id: str = Form(default=""),
):
    redirect = require_login(request)
    if redirect:
        return redirect
    get_accessible_guild(request, guild_id)

    streamer = streamer.strip()
    if not streamer or not channel_id.isdigit() or (
        mention_role_id and not mention_role_id.isdigit()
    ):
        return RedirectResponse(f"/server/{guild_id}?kick_error=invalid#kick", status_code=303)
    resources = await get_bot_guild_resources(guild_id)
    if resources["available"]:
        allowed_channels = {
            str(channel["id"])
            for channel in resources["channels"]
            if channel.get("can_send")
        }
        allowed_roles = {str(role["id"]) for role in resources["roles"]}
        if channel_id not in allowed_channels or (
            mention_role_id and mention_role_id not in allowed_roles
        ):
            return RedirectResponse(
                f"/server/{guild_id}?kick_error=invalid#kick", status_code=303
            )
    try:
        channel = await kick_api.get_channel(streamer)
    except (KickAPIError, aiohttp.ClientError, asyncio.TimeoutError, OSError):
        return RedirectResponse(f"/server/{guild_id}?kick_error=api#kick", status_code=303)
    if channel is None:
        return RedirectResponse(f"/server/{guild_id}?kick_error=not-found#kick", status_code=303)

    await asyncio.to_thread(
        kick_store.add,
        int(guild_id),
        channel.user_id,
        channel.slug,
        int(channel_id),
        int(mention_role_id) if mention_role_id else None,
    )
    return RedirectResponse(f"/server/{guild_id}?saved=kick#kick", status_code=303)


@app.post("/server/{guild_id}/kick/remove")
async def remove_kick_subscription(
    request: Request,
    guild_id: str,
    streamer_slug: str = Form(default=""),
):
    redirect = require_login(request)
    if redirect:
        return redirect
    get_accessible_guild(request, guild_id)
    await asyncio.to_thread(
        kick_store.remove, int(guild_id), kick_api.normalize_slug(streamer_slug)
    )
    return RedirectResponse(f"/server/{guild_id}?saved=kick-remove#kick", status_code=303)


@app.post("/server/{guild_id}/avatar")
async def save_bot_avatar(
    request: Request,
    guild_id: str,
    avatar: UploadFile = File(...),
):
    redirect = require_login(request)
    if redirect:
        return redirect

    get_accessible_guild(request, guild_id)
    content_type = (avatar.content_type or "").lower()
    if content_type not in ALLOWED_AVATAR_TYPES:
        return RedirectResponse(
            f"/server/{guild_id}?avatar_error=type#appearance",
            status_code=303,
        )

    content = await avatar.read(MAX_AVATAR_SIZE + 1)
    await avatar.close()
    if not content or len(content) > MAX_AVATAR_SIZE:
        return RedirectResponse(
            f"/server/{guild_id}?avatar_error=size#appearance",
            status_code=303,
        )
    if not valid_avatar_image(content_type, content):
        return RedirectResponse(
            f"/server/{guild_id}?avatar_error=type#appearance",
            status_code=303,
        )

    encoded = base64.b64encode(content).decode("ascii")
    data_uri = f"data:{content_type};base64,{encoded}"

    try:
        await set_bot_guild_avatar(guild_id, data_uri)
    except (httpx.HTTPError, RuntimeError):
        return RedirectResponse(
            f"/server/{guild_id}?avatar_error=discord#appearance",
            status_code=303,
        )

    return RedirectResponse(
        f"/server/{guild_id}?saved=avatar#appearance",
        status_code=303,
    )


@app.post("/server/{guild_id}/avatar/reset")
async def reset_bot_avatar(request: Request, guild_id: str):
    redirect = require_login(request)
    if redirect:
        return redirect

    get_accessible_guild(request, guild_id)
    try:
        await set_bot_guild_avatar(guild_id, None)
    except (httpx.HTTPError, RuntimeError):
        return RedirectResponse(
            f"/server/{guild_id}?avatar_error=discord#appearance",
            status_code=303,
        )

    return RedirectResponse(
        f"/server/{guild_id}?saved=avatar-reset#appearance",
        status_code=303,
    )


@app.post("/server/{guild_id}/welcome")
async def save_welcome(
    request: Request,
    guild_id: str,
    enabled: str | None = Form(default=None),
    channel_id: str = Form(default=""),
    message: str = Form(default="Vítej {mention} na serveru {server}!"),
    embed_title: str = Form(default="Vítej!"),
    embed_color: str = Form(default="#5865F2"),
    dm_enabled: str | None = Form(default=None),
):
    redirect = require_login(request)
    if redirect:
        return redirect

    get_accessible_guild(request, guild_id)
    is_enabled = enabled == "on"
    selected_channel_id = channel_id.strip()
    saved_unverified = False

    if is_enabled:
        if not selected_channel_id.isdigit():
            return RedirectResponse(
                f"/server/{guild_id}?welcome_error=channel#welcome",
                status_code=303,
            )
        resources = await get_bot_guild_resources(guild_id)
        if not resources["available"]:
            saved_unverified = True
        else:
            selected_channel = next(
                (
                    channel
                    for channel in resources["channels"]
                    if channel["id"] == selected_channel_id
                ),
                None,
            )
            if selected_channel is None or not selected_channel["can_send"]:
                return RedirectResponse(
                    f"/server/{guild_id}?welcome_error=channel#welcome",
                    status_code=303,
                )

    await storage.update_module(
        guild_id,
        "welcome",
        {
            "enabled": is_enabled,
            "channel_id": selected_channel_id,
            "message": message.strip(),
            "embed_title": embed_title.strip(),
            "embed_color": embed_color.strip(),
            "dm_enabled": dm_enabled == "on",
        },
    )
    query = "saved=welcome"
    if saved_unverified:
        query += "&welcome_warning=unverified"
    return RedirectResponse(f"/server/{guild_id}?{query}#welcome", status_code=303)


@app.post("/server/{guild_id}/youtube")
async def save_youtube(
    request: Request,
    guild_id: str,
    enabled: str | None = Form(default=None),
    channel_id: str = Form(default=""),
    youtube_channel_id: str = Form(default=""),
    custom_message: str = Form(default="📺 Nové video: {title}\\n{url}"),
    mention_role_id: str = Form(default=""),
    check_interval: int = Form(default=300),
    live_enabled: str | None = Form(default=None),
    live_notify_upcoming: str | None = Form(default=None),
    live_custom_message: str = Form(default="🔴 {channel} právě vysílá: {title}\\n{url}"),
):
    redirect = require_login(request)
    if redirect:
        return redirect

    get_accessible_guild(request, guild_id)

    check_interval = max(60, min(int(check_interval), 3600))
    is_enabled = enabled == "on"
    selected_channel_id = channel_id.strip()
    selected_role_id = mention_role_id.strip()
    selected_youtube_id = youtube_channel_id.strip()
    saved_unverified = False

    if selected_channel_id and not selected_channel_id.isdigit():
        return RedirectResponse(
            f"/server/{guild_id}?youtube_error=channel#youtube",
            status_code=303,
        )
    if selected_role_id and not selected_role_id.isdigit():
        return RedirectResponse(
            f"/server/{guild_id}?youtube_error=role#youtube",
            status_code=303,
        )
    if is_enabled and not re.fullmatch(r"UC[A-Za-z0-9_-]{22}", selected_youtube_id):
        return RedirectResponse(
            f"/server/{guild_id}?youtube_error=youtube#youtube",
            status_code=303,
        )
    if is_enabled:
        if not selected_channel_id:
            return RedirectResponse(
                f"/server/{guild_id}?youtube_error=channel#youtube",
                status_code=303,
            )
        resources = await get_bot_guild_resources(guild_id)
        if not resources["available"]:
            saved_unverified = True
        else:
            allowed_channels = {
                channel["id"] for channel in resources["channels"] if channel["can_send"]
            }
            allowed_roles = {role["id"] for role in resources["roles"]}
            if selected_channel_id not in allowed_channels:
                return RedirectResponse(
                    f"/server/{guild_id}?youtube_error=channel#youtube",
                    status_code=303,
                )
            if selected_role_id and selected_role_id not in allowed_roles:
                return RedirectResponse(
                    f"/server/{guild_id}?youtube_error=role#youtube",
                    status_code=303,
                )

    await storage.update_module(
        guild_id,
        "youtube",
        {
            "enabled": is_enabled,
            "channel_id": selected_channel_id,
            "youtube_channel_id": selected_youtube_id,
            "custom_message": custom_message.strip(),
            "mention_role_id": selected_role_id,
            "check_interval": check_interval,
            "live_enabled": live_enabled == "on",
            "live_notify_upcoming": live_notify_upcoming == "on",
            "live_custom_message": live_custom_message.strip(),
        },
    )

    query = "saved=youtube"
    if saved_unverified:
        query += "&youtube_warning=unverified"
    return RedirectResponse(f"/server/{guild_id}?{query}#youtube", status_code=303)


@app.post("/server/{guild_id}/autorole")
async def save_autorole(
    request: Request,
    guild_id: str,
    enabled: str | None = Form(default=None),
    role_id: str = Form(default=""),
):
    redirect = require_login(request)
    if redirect:
        return redirect

    get_accessible_guild(request, guild_id)
    is_enabled = enabled == "on"
    selected_role_id = role_id.strip()
    saved_unverified = False

    if is_enabled:
        resources = await get_bot_guild_resources(guild_id)
        if not resources["available"]:
            saved_unverified = True
        elif not resources["can_manage_roles"]:
            return RedirectResponse(
                f"/server/{guild_id}?autorole_error=permission#autorole",
                status_code=303,
            )
        else:
            selected_role = next(
                (role for role in resources["roles"] if role["id"] == selected_role_id),
                None,
            )
            if selected_role is None:
                return RedirectResponse(
                    f"/server/{guild_id}?autorole_error=role#autorole",
                    status_code=303,
                )
            if not selected_role["assignable"]:
                return RedirectResponse(
                    f"/server/{guild_id}?autorole_error=hierarchy#autorole",
                    status_code=303,
                )

    await storage.update_module(
        guild_id,
        "autorole",
        {"enabled": is_enabled, "role_id": selected_role_id},
    )
    query = "saved=autorole"
    if saved_unverified:
        query += "&autorole_warning=unverified"
    return RedirectResponse(f"/server/{guild_id}?{query}#autorole", status_code=303)


@app.post("/server/{guild_id}/modlogs")
async def save_modlogs(
    request: Request,
    guild_id: str,
    enabled: str | None = Form(default=None),
    channel_id: str = Form(default=""),
    log_members: str | None = Form(default=None),
    log_messages: str | None = Form(default=None),
    log_voice: str | None = Form(default=None),
    log_channels: str | None = Form(default=None),
    log_bans: str | None = Form(default=None),
):
    redirect = require_login(request)
    if redirect:
        return redirect

    get_accessible_guild(request, guild_id)
    is_enabled = enabled == "on"
    selected_channel_id = channel_id.strip()
    saved_unverified = False

    if is_enabled:
        if not selected_channel_id.isdigit():
            return RedirectResponse(
                f"/server/{guild_id}?modlogs_error=channel#modlogs",
                status_code=303,
            )
        resources = await get_bot_guild_resources(guild_id)
        if not resources["available"]:
            saved_unverified = True
        else:
            allowed_channels = {
                channel["id"] for channel in resources["channels"] if channel["can_send"]
            }
            if selected_channel_id not in allowed_channels:
                return RedirectResponse(
                    f"/server/{guild_id}?modlogs_error=channel#modlogs",
                    status_code=303,
                )

    await storage.update_module(
        guild_id,
        "modlogs",
        {
            "enabled": is_enabled,
            "channel_id": selected_channel_id,
            "log_members": log_members == "on",
            "log_messages": log_messages == "on",
            "log_voice": log_voice == "on",
            "log_channels": log_channels == "on",
            "log_bans": log_bans == "on",
        },
    )
    query = "saved=modlogs"
    if saved_unverified:
        query += "&modlogs_warning=unverified"
    return RedirectResponse(f"/server/{guild_id}?{query}#modlogs", status_code=303)


@app.post("/server/{guild_id}/antispam")
async def save_antispam(
    request: Request,
    guild_id: str,
    enabled: str | None = Form(default=None),
    max_messages: int = Form(default=6),
    interval_seconds: int = Form(default=8),
    duplicate_limit: int = Form(default=3),
    mention_limit: int = Form(default=5),
    timeout_minutes: int = Form(default=10),
    delete_messages: str | None = Form(default=None),
    ignored_channel_ids: list[str] = Form(default=[]),
):
    redirect = require_login(request)
    if redirect:
        return redirect

    get_accessible_guild(request, guild_id)
    await storage.update_module(
        guild_id,
        "antispam",
        {
            "enabled": enabled == "on",
            "max_messages": max_messages,
            "interval_seconds": interval_seconds,
            "duplicate_limit": duplicate_limit,
            "mention_limit": mention_limit,
            "timeout_minutes": timeout_minutes,
            "delete_messages": delete_messages == "on",
            "ignored_channel_ids": ignored_channel_ids,
        },
    )
    return RedirectResponse(
        f"/server/{guild_id}?saved=antispam#antispam",
        status_code=303,
    )


@app.post("/server/{guild_id}/tickets")
async def save_tickets(
    request: Request,
    guild_id: str,
    enabled: str | None = Form(default=None),
    panel_channel_id: str = Form(default=""),
    category_id: str = Form(default=""),
    support_role_id: str = Form(default=""),
    log_channel_id: str = Form(default=""),
):
    redirect = require_login(request)
    if redirect:
        return redirect

    get_accessible_guild(request, guild_id)
    is_enabled = enabled == "on"
    panel_id = panel_channel_id.strip()
    selected_category_id = category_id.strip()
    selected_support_role_id = support_role_id.strip()
    selected_log_channel_id = log_channel_id.strip()
    saved_unverified = False

    required_ids = (panel_id, selected_category_id, selected_support_role_id)
    all_ids = (*required_ids, selected_log_channel_id)
    if any(value and not value.isdigit() for value in all_ids) or (
        is_enabled and not all(required_ids)
    ):
        return RedirectResponse(
            f"/server/{guild_id}?tickets_error=invalid#tickets",
            status_code=303,
        )

    if is_enabled:
        resources = await get_bot_guild_resources(guild_id)
        if not resources["available"]:
            saved_unverified = True
        else:
            allowed_channels = {
                channel["id"] for channel in resources["channels"] if channel["can_send"]
            }
            allowed_categories = {category["id"] for category in resources["categories"]}
            allowed_roles = {role["id"] for role in resources["roles"]}
            invalid_selection = (
                panel_id not in allowed_channels
                or selected_category_id not in allowed_categories
                or selected_support_role_id not in allowed_roles
                or (
                    selected_log_channel_id
                    and selected_log_channel_id not in allowed_channels
                )
            )
            if invalid_selection:
                return RedirectResponse(
                    f"/server/{guild_id}?tickets_error=invalid#tickets",
                    status_code=303,
                )

    await storage.update_module(
        guild_id,
        "tickets",
        {
            "enabled": is_enabled,
            "panel_channel_id": panel_id,
            "category_id": selected_category_id,
            "support_role_id": selected_support_role_id,
            "log_channel_id": selected_log_channel_id,
        },
    )
    query = "saved=tickets"
    if saved_unverified:
        query += "&tickets_warning=unverified"
    return RedirectResponse(f"/server/{guild_id}?{query}#tickets", status_code=303)


@app.post("/server/{guild_id}/pc-advice")
async def save_pc_advice(
    request: Request,
    guild_id: str,
    enabled: str | None = Form(default=None),
    mode: str = Form(default="private"),
    panel_channel_id: str = Form(default=""),
    category_id: str = Form(default=""),
    forum_channel_id: str = Form(default=""),
    advisor_role_id: str = Form(default=""),
    log_channel_id: str = Form(default=""),
    reminders_enabled: str | None = Form(default=None),
    reminder_days: str = Form(default="3"),
):
    redirect = require_login(request)
    if redirect:
        return redirect
    get_accessible_guild(request, guild_id)
    is_enabled = enabled == "on"
    selected_mode = mode.strip()
    panel_id = panel_channel_id.strip()
    selected_category_id = category_id.strip()
    selected_forum_id = forum_channel_id.strip()
    selected_advisor_role_id = advisor_role_id.strip()
    selected_log_channel_id = log_channel_id.strip()
    reminders_are_enabled = reminders_enabled == "on"
    try:
        selected_reminder_days = int(reminder_days)
    except (TypeError, ValueError):
        selected_reminder_days = 0
    saved_unverified = False

    all_ids = (
        panel_id,
        selected_category_id,
        selected_forum_id,
        selected_advisor_role_id,
        selected_log_channel_id,
    )
    required_missing = is_enabled and (
        not panel_id
        or not selected_advisor_role_id
        or (selected_mode == "private" and not selected_category_id)
        or (selected_mode == "forum" and not selected_forum_id)
        or (
            selected_mode == "choice"
            and (not selected_category_id or not selected_forum_id)
        )
    )
    if (
        selected_mode not in {"private", "forum", "choice"}
        or any(value and not value.isdigit() for value in all_ids)
        or required_missing
        or not 1 <= selected_reminder_days <= 30
    ):
        return RedirectResponse(
            f"/server/{guild_id}?pc_advice_error=invalid#pc-advice",
            status_code=303,
        )

    if is_enabled:
        resources = await get_bot_guild_resources(guild_id)
        if not resources["available"]:
            saved_unverified = True
        else:
            allowed_channels = {
                channel["id"] for channel in resources["channels"] if channel["can_send"]
            }
            allowed_categories = {category["id"] for category in resources["categories"]}
            allowed_forums = {
                forum["id"] for forum in resources["forums"] if forum["can_post"]
            }
            allowed_roles = {role["id"] for role in resources["roles"]}
            invalid_selection = (
                panel_id not in allowed_channels
                or selected_advisor_role_id not in allowed_roles
                or (
                    selected_log_channel_id
                    and selected_log_channel_id not in allowed_channels
                )
                or (
                    selected_mode in {"private", "choice"}
                    and selected_category_id not in allowed_categories
                )
                or (
                    selected_mode in {"forum", "choice"}
                    and selected_forum_id not in allowed_forums
                )
            )
            if invalid_selection:
                return RedirectResponse(
                    f"/server/{guild_id}?pc_advice_error=invalid#pc-advice",
                    status_code=303,
                )
    await storage.update_module(
        guild_id,
        "pc_advice",
        {
            "enabled": is_enabled,
            "mode": selected_mode,
            "panel_channel_id": panel_id,
            "category_id": selected_category_id,
            "forum_channel_id": selected_forum_id,
            "advisor_role_id": selected_advisor_role_id,
            "log_channel_id": selected_log_channel_id,
            "reminders_enabled": reminders_are_enabled,
            "reminder_days": selected_reminder_days,
        },
    )
    query = "saved=pc-advice"
    if saved_unverified:
        query += "&pc_advice_warning=unverified"
    return RedirectResponse(f"/server/{guild_id}?{query}#pc-advice", status_code=303)


@app.post("/server/{guild_id}/abi-rank")
async def save_abi_rank(
    request: Request,
    guild_id: str,
    enabled: str | None = Form(default=None),
    review_channel_id: str = Form(default=""),
    reviewer_role_id: str = Form(default=""),
    rookie_role_id: str = Form(default=""),
    vanguard_role_id: str = Form(default=""),
    elite_role_id: str = Form(default=""),
    expert_role_id: str = Form(default=""),
    master_role_id: str = Form(default=""),
    ace_role_id: str = Form(default=""),
    hero_role_id: str = Form(default=""),
    legend_role_id: str = Form(default=""),
):
    redirect = require_login(request)
    if redirect:
        return redirect
    get_accessible_guild(request, guild_id)
    is_enabled = enabled == "on"
    selected_review_channel_id = review_channel_id.strip()
    selected_reviewer_role_id = reviewer_role_id.strip()
    rank_roles = {
        "rookie": rookie_role_id.strip(),
        "vanguard": vanguard_role_id.strip(),
        "elite": elite_role_id.strip(),
        "expert": expert_role_id.strip(),
        "master": master_role_id.strip(),
        "ace": ace_role_id.strip(),
        "hero": hero_role_id.strip(),
        "legend": legend_role_id.strip(),
    }
    all_ids = (
        selected_review_channel_id,
        selected_reviewer_role_id,
        *rank_roles.values(),
    )
    saved_unverified = False

    if any(value and not value.isdigit() for value in all_ids) or (
        is_enabled and (not selected_review_channel_id or not selected_reviewer_role_id)
    ):
        return RedirectResponse(
            f"/server/{guild_id}?abi_rank_error=invalid#abi-rank",
            status_code=303,
        )

    if is_enabled:
        resources = await get_bot_guild_resources(guild_id)
        if not resources["available"]:
            saved_unverified = True
        else:
            allowed_channels = {
                channel["id"] for channel in resources["channels"] if channel["can_send"]
            }
            existing_roles = {role["id"] for role in resources["roles"]}
            assignable_roles = {
                role["id"] for role in resources["roles"] if role["assignable"]
            }
            selected_rank_roles = {role_id for role_id in rank_roles.values() if role_id}

            if (
                selected_review_channel_id not in allowed_channels
                or selected_reviewer_role_id not in existing_roles
            ):
                return RedirectResponse(
                    f"/server/{guild_id}?abi_rank_error=invalid#abi-rank",
                    status_code=303,
                )
            if selected_rank_roles and not resources["can_manage_roles"]:
                return RedirectResponse(
                    f"/server/{guild_id}?abi_rank_error=permission#abi-rank",
                    status_code=303,
                )
            if not selected_rank_roles.issubset(assignable_roles):
                return RedirectResponse(
                    f"/server/{guild_id}?abi_rank_error=hierarchy#abi-rank",
                    status_code=303,
                )
    await storage.update_module(guild_id, "abi_rank", {
        "enabled": is_enabled,
        "review_channel_id": selected_review_channel_id,
        "reviewer_role_id": selected_reviewer_role_id,
        **{f"{rank}_role_id": role_id for rank, role_id in rank_roles.items()},
    })
    query = "saved=abi-rank"
    if saved_unverified:
        query += "&abi_rank_warning=unverified"
    return RedirectResponse(f"/server/{guild_id}?{query}#abi-rank", status_code=303)


@app.post("/server/{guild_id}/moderation")
async def save_moderation(
    request: Request, guild_id: str,
    auto_punishments: str | None = Form(default=None),
):
    redirect = require_login(request)
    if redirect:
        return redirect
    get_accessible_guild(request, guild_id)
    await storage.update_module(
        guild_id, "moderation", {"auto_punishments": auto_punishments == "on"}
    )
    return RedirectResponse(
        f"/server/{guild_id}?saved=moderation#moderation", status_code=303
    )


@app.post("/server/{guild_id}/general")
async def save_general(
    request: Request,
    guild_id: str,
    language: str = Form(default="cs"),
    timezone: str = Form(default="Europe/Prague"),
    command_channel_id: str = Form(default=""),
):
    redirect = require_login(request)
    if redirect:
        return redirect

    get_accessible_guild(request, guild_id)

    selected_language = language.strip().lower()
    selected_timezone = timezone.strip() or "Europe/Prague"
    selected_command_channel_id = command_channel_id.strip()
    saved_unverified = False

    if selected_language not in {"cs", "sk", "en"}:
        return RedirectResponse(
            f"/server/{guild_id}?general_error=language#general",
            status_code=303,
        )
    try:
        ZoneInfo(selected_timezone)
    except (ZoneInfoNotFoundError, ValueError):
        return RedirectResponse(
            f"/server/{guild_id}?general_error=timezone#general",
            status_code=303,
        )
    if selected_command_channel_id:
        if not selected_command_channel_id.isdigit():
            return RedirectResponse(
                f"/server/{guild_id}?general_error=channel#general",
                status_code=303,
            )
        resources = await get_bot_guild_resources(guild_id)
        if not resources["available"]:
            saved_unverified = True
        else:
            allowed_channels = {
                channel["id"] for channel in resources["channels"] if channel["can_send"]
            }
            if selected_command_channel_id not in allowed_channels:
                return RedirectResponse(
                    f"/server/{guild_id}?general_error=channel#general",
                    status_code=303,
                )

    await storage.update_module(
        guild_id,
        "general",
        {
            "language": selected_language,
            "timezone": selected_timezone,
            "command_channel_id": selected_command_channel_id,
        },
    )

    query = "saved=general"
    if saved_unverified:
        query += "&general_warning=unverified"
    return RedirectResponse(f"/server/{guild_id}?{query}#general", status_code=303)


@app.get("/api/server/{guild_id}/settings")
async def api_get_settings(request: Request, guild_id: str):
    redirect = require_login(request)
    if redirect:
        return JSONResponse({"detail": "Unauthorized"}, status_code=401)

    get_accessible_guild(request, guild_id)
    return await storage.get_settings(guild_id)


@app.get("/api/bot/config/{guild_id}")
async def bot_config(guild_id: str, request: Request):
    expected = os.getenv("DASHBOARD_BOT_API_KEY", "")
    provided = request.headers.get("X-Piticko-Key", "")

    if not expected or provided != expected:
        raise HTTPException(status_code=401, detail="Neplatný API klíč.")

    return await storage.get_settings(guild_id)
