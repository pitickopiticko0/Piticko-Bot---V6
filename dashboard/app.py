import os
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, Form, HTTPException, Request
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

    return templates.TemplateResponse(
        request=request,
        name="server.html",
        context={
            "page_title": guild.get("name", "Server"),
            "user": current_user(request),
            "guild": guild,
            "settings": settings,
        },
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
