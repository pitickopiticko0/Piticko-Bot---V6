import os
from pathlib import Path
from typing import Optional
from urllib.parse import quote

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from config import CHECK_INTERVAL, DATABASE, LOG_FILE, VERSION, YOUTUBE_API_KEY
from dashboard.auth import get_user, require_user, router as auth_router
from dashboard.api.health import router as health_router
from dashboard.api.stats import router as stats_router
from dashboard.api.welcome import router as welcome_router
from dashboard.api.youtube import router as youtube_router
from utils.database import db
from utils.youtube_api import YouTubeAPIError, youtube_api


BASE_DIR = Path(__file__).parent
SECRET_KEY = os.getenv("DASHBOARD_SECRET_KEY", "change-this-dashboard-secret-key")

app = FastAPI(title="Piticko Bot Dashboard", version=VERSION)

app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET_KEY,
    same_site="lax",
    https_only=False,
)

app.include_router(auth_router)
app.include_router(health_router)
app.include_router(stats_router)
app.include_router(youtube_router)
app.include_router(welcome_router)

templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
static_dir = BASE_DIR / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


def redirect_with_message(url: str, status: str, message: str) -> RedirectResponse:
    return RedirectResponse(f"{url}?status={status}&message={quote(message)}", status_code=303)


def get_session_guilds(request: Request) -> list[dict]:
    return request.session.get("guilds", [])


def get_selected_guild(request: Request, guild_id: int) -> dict | None:
    for guild in get_session_guilds(request):
        if str(guild.get("id")) == str(guild_id):
            return guild
    return None


def get_youtube_rows(guild_id: int):
    with db.connect() as conn:
        return conn.execute("""
            SELECT
                s.guild_id,
                s.youtube_channel_id,
                s.discord_channel_id,
                s.mention_role_id,
                s.last_video_id,
                s.enabled,
                y.youtube_name,
                y.youtube_url
            FROM subscriptions s
            JOIN youtube_channels y
                ON y.youtube_channel_id = s.youtube_channel_id
            WHERE s.guild_id = ?
            ORDER BY y.youtube_name ASC
        """, (guild_id,)).fetchall()


def get_welcome_settings(guild_id: int):
    with db.connect() as conn:
        return conn.execute("""
            SELECT
                w.guild_id,
                w.channel_id,
                w.role_id,
                w.enabled,
                w.message,
                w.updated_at,
                g.guild_name
            FROM welcome_settings w
            LEFT JOIN guilds g
                ON g.guild_id = w.guild_id
            WHERE w.guild_id = ?
        """, (guild_id,)).fetchone()


def get_guild_stats(guild_id: int):
    with db.connect() as conn:
        youtube_subscriptions = conn.execute("""
            SELECT COUNT(*) AS c
            FROM subscriptions
            WHERE guild_id = ?
        """, (guild_id,)).fetchone()["c"]

        active_youtube_subscriptions = conn.execute("""
            SELECT COUNT(*) AS c
            FROM subscriptions
            WHERE guild_id = ? AND enabled = 1
        """, (guild_id,)).fetchone()["c"]

        welcome = conn.execute("""
            SELECT enabled
            FROM welcome_settings
            WHERE guild_id = ?
        """, (guild_id,)).fetchone()

        return {
            "youtube_subscriptions": youtube_subscriptions,
            "active_youtube_subscriptions": active_youtube_subscriptions,
            "welcome_enabled": bool(welcome["enabled"]) if welcome else False,
        }


@app.get("/test")
async def test():
    return {"ok": True, "app": "dashboard.app", "version": VERSION}


@app.get("/login-page", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html", {"version": VERSION})


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    redirect = require_user(request)
    if redirect:
        return redirect

    stats = db.stats()
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "version": VERSION,
            "stats": stats,
            "active": "dashboard",
            "user": get_user(request),
            "guilds": get_session_guilds(request),
            "selected_guild": None,
        },
    )


@app.get("/youtube")
async def old_youtube_redirect(request: Request):
    redirect = require_user(request)
    if redirect:
        return redirect

    guilds = get_session_guilds(request)
    if guilds:
        return RedirectResponse(f"/guild/{guilds[0]['id']}/youtube", status_code=303)
    return RedirectResponse("/", status_code=303)


@app.get("/welcome")
async def old_welcome_redirect(request: Request):
    redirect = require_user(request)
    if redirect:
        return redirect

    guilds = get_session_guilds(request)
    if guilds:
        return RedirectResponse(f"/guild/{guilds[0]['id']}/welcome", status_code=303)
    return RedirectResponse("/", status_code=303)


@app.get("/guild/{guild_id}", response_class=HTMLResponse)
async def guild_dashboard(request: Request, guild_id: int):
    redirect = require_user(request)
    if redirect:
        return redirect

    selected_guild = get_selected_guild(request, guild_id)
    if selected_guild is None:
        return RedirectResponse("/", status_code=303)

    stats = get_guild_stats(guild_id)
    return templates.TemplateResponse(
        request,
        "guild.html",
        {
            "version": VERSION,
            "active": "guild",
            "user": get_user(request),
            "guilds": get_session_guilds(request),
            "selected_guild": selected_guild,
            "stats": stats,
        },
    )


@app.get("/guild/{guild_id}/youtube", response_class=HTMLResponse)
async def guild_youtube_page(
    request: Request,
    guild_id: int,
    status: Optional[str] = None,
    message: Optional[str] = None,
):
    redirect = require_user(request)
    if redirect:
        return redirect

    selected_guild = get_selected_guild(request, guild_id)
    if selected_guild is None:
        return RedirectResponse("/", status_code=303)

    rows = get_youtube_rows(guild_id)
    return templates.TemplateResponse(
        request,
        "guild_youtube.html",
        {
            "version": VERSION,
            "rows": rows,
            "active": "guild_youtube",
            "status": status,
            "message": message,
            "user": get_user(request),
            "guilds": get_session_guilds(request),
            "selected_guild": selected_guild,
        },
    )


@app.post("/guild/{guild_id}/youtube/add")
async def guild_youtube_add(
    request: Request,
    guild_id: int,
    youtube_url: str = Form(...),
    discord_channel_id: int = Form(...),
    mention_role_id: str = Form(""),
):
    redirect = require_user(request)
    if redirect:
        return redirect

    selected_guild = get_selected_guild(request, guild_id)
    if selected_guild is None:
        return RedirectResponse("/", status_code=303)

    try:
        clean_mention_role_id = int(mention_role_id) if mention_role_id.strip() else None
    except ValueError:
        return redirect_with_message(f"/guild/{guild_id}/youtube", "error", "Role ID musí být číslo nebo prázdné.")

    try:
        yt_channel = await youtube_api.resolve_channel(youtube_url)
        db.add_guild(guild_id=guild_id, guild_name=selected_guild.get("name") or "Discord Server")
        db.add_youtube_channel(channel_id=yt_channel.id, name=yt_channel.title, url=yt_channel.url)
        db.add_subscription(
            guild_id=guild_id,
            youtube_channel_id=yt_channel.id,
            discord_channel_id=discord_channel_id,
            mention_role_id=clean_mention_role_id,
        )
        return redirect_with_message(f"/guild/{guild_id}/youtube", "success", f"Kanál {yt_channel.title} byl přidán.")
    except YouTubeAPIError as e:
        return redirect_with_message(f"/guild/{guild_id}/youtube", "error", f"YouTube chyba: {e}")
    except Exception as e:
        return redirect_with_message(f"/guild/{guild_id}/youtube", "error", f"Chyba: {e}")


@app.post("/guild/{guild_id}/youtube/remove")
async def guild_youtube_remove(request: Request, guild_id: int, youtube_channel_id: str = Form(...)):
    redirect = require_user(request)
    if redirect:
        return redirect

    if get_selected_guild(request, guild_id) is None:
        return RedirectResponse("/", status_code=303)

    removed = db.remove_subscription(guild_id=guild_id, youtube_channel_id=youtube_channel_id)
    if removed:
        return redirect_with_message(f"/guild/{guild_id}/youtube", "success", "Odběr byl odebrán.")
    return redirect_with_message(f"/guild/{guild_id}/youtube", "error", "Odběr nebyl nalezen.")


@app.post("/guild/{guild_id}/youtube/pause")
async def guild_youtube_pause(request: Request, guild_id: int, youtube_channel_id: str = Form(...)):
    redirect = require_user(request)
    if redirect:
        return redirect

    if get_selected_guild(request, guild_id) is None:
        return RedirectResponse("/", status_code=303)

    db.pause_subscription(guild_id=guild_id, youtube_channel_id=youtube_channel_id)
    return redirect_with_message(f"/guild/{guild_id}/youtube", "success", "Odběr byl pozastaven.")


@app.post("/guild/{guild_id}/youtube/resume")
async def guild_youtube_resume(request: Request, guild_id: int, youtube_channel_id: str = Form(...)):
    redirect = require_user(request)
    if redirect:
        return redirect

    if get_selected_guild(request, guild_id) is None:
        return RedirectResponse("/", status_code=303)

    db.resume_subscription(guild_id=guild_id, youtube_channel_id=youtube_channel_id)
    return redirect_with_message(f"/guild/{guild_id}/youtube", "success", "Odběr byl znovu zapnut.")


@app.get("/guild/{guild_id}/welcome", response_class=HTMLResponse)
async def guild_welcome_page(
    request: Request,
    guild_id: int,
    status: Optional[str] = None,
    message: Optional[str] = None,
):
    redirect = require_user(request)
    if redirect:
        return redirect

    selected_guild = get_selected_guild(request, guild_id)
    if selected_guild is None:
        return RedirectResponse("/", status_code=303)

    settings = get_welcome_settings(guild_id)
    return templates.TemplateResponse(
        request,
        "guild_welcome.html",
        {
            "version": VERSION,
            "settings": settings,
            "active": "guild_welcome",
            "status": status,
            "message": message,
            "user": get_user(request),
            "guilds": get_session_guilds(request),
            "selected_guild": selected_guild,
        },
    )


@app.post("/guild/{guild_id}/welcome/save")
async def guild_welcome_save(
    request: Request,
    guild_id: int,
    channel_id: int = Form(...),
    role_id: str = Form(""),
    welcome_message: str = Form(...),
):
    redirect = require_user(request)
    if redirect:
        return redirect

    selected_guild = get_selected_guild(request, guild_id)
    if selected_guild is None:
        return RedirectResponse("/", status_code=303)

    try:
        clean_role_id = int(role_id) if role_id.strip() else None
    except ValueError:
        return redirect_with_message(f"/guild/{guild_id}/welcome", "error", "Role ID musí být číslo nebo prázdné.")

    db.add_guild(guild_id=guild_id, guild_name=selected_guild.get("name") or "Discord Server")
    db.set_welcome_settings(
        guild_id=guild_id,
        channel_id=channel_id,
        role_id=clean_role_id,
        message=welcome_message,
    )

    with db.connect() as conn:
        conn.execute("""
            UPDATE welcome_settings
            SET enabled = 1
            WHERE guild_id = ?
        """, (guild_id,))
        conn.commit()

    return redirect_with_message(f"/guild/{guild_id}/welcome", "success", "Welcome nastavení bylo uloženo a zapnuto.")


@app.post("/guild/{guild_id}/welcome/disable")
async def guild_welcome_disable(request: Request, guild_id: int):
    redirect = require_user(request)
    if redirect:
        return redirect

    if get_selected_guild(request, guild_id) is None:
        return RedirectResponse("/", status_code=303)

    db.disable_welcome(guild_id)
    return redirect_with_message(f"/guild/{guild_id}/welcome", "success", "Welcome systém byl vypnut.")


@app.post("/guild/{guild_id}/welcome/enable")
async def guild_welcome_enable(request: Request, guild_id: int):
    redirect = require_user(request)
    if redirect:
        return redirect

    if get_selected_guild(request, guild_id) is None:
        return RedirectResponse("/", status_code=303)

    if hasattr(db, "enable_welcome"):
        db.enable_welcome(guild_id)
    else:
        with db.connect() as conn:
            conn.execute("""
                UPDATE welcome_settings
                SET enabled = 1
                WHERE guild_id = ?
            """, (guild_id,))
            conn.commit()

    return redirect_with_message(f"/guild/{guild_id}/welcome", "success", "Welcome systém byl zapnut.")


@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    redirect = require_user(request)
    if redirect:
        return redirect

    settings = {
        "version": VERSION,
        "check_interval": CHECK_INTERVAL,
        "database": str(DATABASE),
        "database_exists": Path(DATABASE).exists(),
        "log_file": str(LOG_FILE),
        "log_file_exists": Path(LOG_FILE).exists(),
        "youtube_api_key": bool(YOUTUBE_API_KEY),
        "postgres_enabled": bool(os.getenv("DATABASE_URL")),
    }

    return templates.TemplateResponse(
        request,
        "settings.html",
        {
            "version": VERSION,
            "settings": settings,
            "active": "settings",
            "user": get_user(request),
            "guilds": get_session_guilds(request),
            "selected_guild": None,
        },
    )
