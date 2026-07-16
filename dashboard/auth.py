import os
from urllib.parse import urlencode

import httpx
from dotenv import load_dotenv
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse


load_dotenv()

DISCORD_API = "https://discord.com/api"
DISCORD_AUTH_URL = "https://discord.com/oauth2/authorize"
DISCORD_TOKEN_URL = f"{DISCORD_API}/oauth2/token"

CLIENT_ID = os.getenv("DISCORD_CLIENT_ID")
CLIENT_SECRET = os.getenv("DISCORD_CLIENT_SECRET")
REDIRECT_URI = os.getenv(
    "DASHBOARD_REDIRECT_URI",
    "http://127.0.0.1:8000/auth/callback",
)

router = APIRouter(tags=["auth"])


def is_dashboard_configured() -> bool:
    return bool(CLIENT_ID and CLIENT_SECRET and REDIRECT_URI)


def build_login_url() -> str:
    params = {
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": "identify guilds",
        "prompt": "consent",
    }

    url = f"{DISCORD_AUTH_URL}?{urlencode(params)}"

    print("==== OAUTH DEBUG ====")
    print("CLIENT_ID:", CLIENT_ID)
    print("REDIRECT_URI:", REDIRECT_URI)
    print("LOGIN_URL:", url)
    print("=====================")

    return url


def get_user(request: Request):
    return request.session.get("user")


def require_user(request: Request):
    user = get_user(request)

    if not user:
        return RedirectResponse("/login-page", status_code=303)

    return None


@router.get("/login")
async def login(request: Request):
    if get_user(request):
        return RedirectResponse("/", status_code=303)

    if not is_dashboard_configured():
        return RedirectResponse("/login-error", status_code=303)

    return RedirectResponse(build_login_url(), status_code=303)


@router.get("/login-error")
async def login_error():
    return {
        "error": (
            "Discord OAuth není nastavený. "
            "Zkontroluj DISCORD_CLIENT_ID, DISCORD_CLIENT_SECRET "
            "a DASHBOARD_REDIRECT_URI."
        )
    }


@router.get("/auth/callback")
async def auth_callback(request: Request, code: str | None = None):
    if not code:
        return RedirectResponse("/login-page", status_code=303)

    if not is_dashboard_configured():
        return RedirectResponse("/login-error", status_code=303)

    data = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI,
    }

    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
    }

    async with httpx.AsyncClient() as client:
        token_response = await client.post(
            DISCORD_TOKEN_URL,
            data=data,
            headers=headers,
        )

        if token_response.status_code != 200:
            print("TOKEN ERROR:", token_response.status_code, token_response.text)
            request.session.clear()
            return RedirectResponse("/login-page", status_code=303)

        token_data = token_response.json()
        access_token = token_data["access_token"]

        user_response = await client.get(
            f"{DISCORD_API}/users/@me",
            headers={"Authorization": f"Bearer {access_token}"},
        )

        guilds_response = await client.get(
            f"{DISCORD_API}/users/@me/guilds",
            headers={"Authorization": f"Bearer {access_token}"},
        )

    if user_response.status_code != 200:
        print("USER ERROR:", user_response.status_code, user_response.text)
        request.session.clear()
        return RedirectResponse("/login-page", status_code=303)

    user = user_response.json()
    guilds = guilds_response.json() if guilds_response.status_code == 200 else []

    print("==== DISCORD GUILDS RAW ====")
    for g in guilds:
        print(
            g.get("name"),
            g.get("id"),
            "owner=", g.get("owner"),
            "permissions=", g.get("permissions"),
        )
    print("============================")

    manageable_guilds = []

    for guild in guilds:
        permissions = int(guild.get("permissions", 0))
        is_owner = guild.get("owner", False)
        has_manage_guild = bool(permissions & 0x20)
        has_administrator = bool(permissions & 0x8)

        if is_owner or has_manage_guild or has_administrator:
            manageable_guilds.append(guild)

    request.session["user"] = {
        "id": user["id"],
        "username": user["username"],
        "global_name": user.get("global_name"),
        "avatar": user.get("avatar"),
    }

    request.session["guilds"] = manageable_guilds
    request.session["access_token"] = access_token

    return RedirectResponse("/", status_code=303)


@router.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login-page", status_code=303)
