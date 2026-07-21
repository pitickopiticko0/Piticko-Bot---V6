import asyncio
import base64
import os
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
import httpx
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from dashboard.auth import router as auth_router
from dashboard.storage import DashboardStorage


load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
storage = DashboardStorage()

SECRET_KEY = os.getenv("DASHBOARD_SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError("Chybí proměnná DASHBOARD_SECRET_KEY.")

app = FastAPI(
    title="Piticko Dashboard V3",
    version="3.0.0",
)

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


async def get_bot_guild_resources(guild_id: str) -> dict[str, Any]:
    empty = {
        "profile": None,
        "channels": [],
        "roles": [],
        "available": False,
    }
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            headers = bot_authorization()
            member_response, channels_response, roles_response = await asyncio.gather(
                client.get(
                    f"{DISCORD_API}/guilds/{guild_id}/members/@me",
                    headers=headers,
                ),
                client.get(
                    f"{DISCORD_API}/guilds/{guild_id}/channels",
                    headers=headers,
                ),
                client.get(
                    f"{DISCORD_API}/guilds/{guild_id}/roles",
                    headers=headers,
                ),
            )
        if any(
            response.status_code != 200
            for response in (member_response, channels_response, roles_response)
        ):
            return empty

        member = member_response.json()
        raw_channels = channels_response.json()
        raw_roles = roles_response.json()
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
        roles = [
            {"id": str(role["id"]), "name": role.get("name") or "Role"}
            for role in raw_roles
            if str(role.get("id")) != str(guild_id)
            and not role.get("managed", False)
        ]
        roles.sort(key=lambda item: item["name"].casefold())

        return {
            "profile": {
                "avatar_url": avatar_url(guild_id, member),
                "has_custom_avatar": bool(member.get("avatar")),
            },
            "channels": channels,
            "roles": roles,
            "available": True,
        }
    except (httpx.HTTPError, RuntimeError, TypeError, ValueError):
        return empty


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

    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "page_title": "Přehled",
            "user": current_user(request),
            "guilds": guilds,
            "configured_count": configured,
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
            "discord_roles": discord_resources["roles"],
            "discord_resources_available": discord_resources["available"],
        },
    )


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

    await storage.update_module(
        guild_id,
        "welcome",
        {
            "enabled": enabled == "on",
            "channel_id": channel_id.strip(),
            "message": message.strip(),
            "embed_title": embed_title.strip(),
            "embed_color": embed_color.strip(),
            "dm_enabled": dm_enabled == "on",
        },
    )

    return RedirectResponse(
        f"/server/{guild_id}?saved=welcome",
        status_code=303,
    )


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
):
    redirect = require_login(request)
    if redirect:
        return redirect

    get_accessible_guild(request, guild_id)

    check_interval = max(60, min(int(check_interval), 3600))

    await storage.update_module(
        guild_id,
        "youtube",
        {
            "enabled": enabled == "on",
            "channel_id": channel_id.strip(),
            "youtube_channel_id": youtube_channel_id.strip(),
            "custom_message": custom_message.strip(),
            "mention_role_id": mention_role_id.strip(),
            "check_interval": check_interval,
        },
    )

    return RedirectResponse(
        f"/server/{guild_id}?saved=youtube",
        status_code=303,
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

    await storage.update_module(
        guild_id,
        "general",
        {
            "language": language,
            "timezone": timezone.strip() or "Europe/Prague",
            "command_channel_id": command_channel_id.strip(),
        },
    )

    return RedirectResponse(
        f"/server/{guild_id}?saved=general",
        status_code=303,
    )


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
