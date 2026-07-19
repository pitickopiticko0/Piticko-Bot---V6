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

    print("========== OAUTH CONFIG ==========")
    print("CLIENT_ID:", CLIENT_ID)
    print("REDIRECT_URI:", REDIRECT_URI)
    print("LOGIN_URL:", url)
    print("==================================")

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
            "Discord OAuth není nastavený.\n"
            "Zkontroluj DISCORD_CLIENT_ID,\n"
            "DISCORD_CLIENT_SECRET a\n"
            "DASHBOARD_REDIRECT_URI."
        )
    }


@router.get("/auth/callback")
async def auth_callback(request: Request, code: str | None = None):

    print("\n========== CALLBACK ==========")
    print("CODE:", code)
    print("REDIRECT_URI:", REDIRECT_URI)

    if not code:
        print("ERROR: OAuth code nebyl předán.")
        return RedirectResponse("/login-page", status_code=303)

    if not is_dashboard_configured():
        print("ERROR: Dashboard není správně nakonfigurován.")
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

    async with httpx.AsyncClient(timeout=30) as client:

        print("Žádám Discord o Access Token...")

        token_response = await client.post(
            DISCORD_TOKEN_URL,
            data=data,
            headers=headers,
        )

        print("TOKEN STATUS:", token_response.status_code)
        print("TOKEN BODY:")
        print(token_response.text)

        if token_response.status_code != 200:
            print("OAuth token selhal.")
            request.session.clear()
            return RedirectResponse("/login-page", status_code=303)

        token_data = token_response.json()
        access_token = token_data["access_token"]

        print("Access token získán.")

        user_response = await client.get(
            f"{DISCORD_API}/users/@me",
            headers={
                "Authorization": f"Bearer {access_token}"
            },
        )

        print("USER STATUS:", user_response.status_code)
        print(user_response.text)

        guilds_response = await client.get(
            f"{DISCORD_API}/users/@me/guilds",
            headers={
                "Authorization": f"Bearer {access_token}"
            },
        )

        print("GUILDS STATUS:", guilds_response.status_code)
        print(guilds_response.text)

    if user_response.status_code != 200:
        print("Discord nevrátil uživatele.")
        request.session.clear()
        return RedirectResponse("/login-page", status_code=303)

    user = user_response.json()
    guilds = guilds_response.json() if guilds_response.status_code == 200 else []

    manageable_guilds = []

    print("\n===== GUILDS =====")

    for guild in guilds:
        permissions = int(guild.get("permissions", 0))

        owner = guild.get("owner", False)
        manage = bool(permissions & 0x20)
        admin = bool(permissions & 0x8)

        print(
            guild["name"],
            guild["id"],
            "owner=", owner,
            "manage=", manage,
            "admin=", admin,
        )

        if owner or manage or admin:
            manageable_guilds.append(guild)

    print("==================")

    request.session["user"] = {
        "id": user["id"],
        "username": user["username"],
        "global_name": user.get("global_name"),
        "avatar": user.get("avatar"),
    }

    request.session["guilds"] = manageable_guilds
    request.session["access_token"] = access_token

    print("LOGIN SUCCESS")
    print("User:", user["username"])
    print("Serverů:", len(manageable_guilds))
    print("==============================\n")

    return RedirectResponse("/", status_code=303)


@router.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login-page", status_code=303)
