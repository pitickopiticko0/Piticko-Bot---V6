import json
import os
import secrets
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


def build_login_url(state: str) -> str:
    params = {
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": "identify guilds",
        "prompt": "consent",
        "state": state,
    }

    url = f"{DISCORD_AUTH_URL}?{urlencode(params)}"

    print("==== OAUTH DEBUG ====")
    print("CLIENT_ID:", CLIENT_ID)
    print("REDIRECT_URI:", REDIRECT_URI)
    print("=====================")

    return url


def get_user(request: Request):
    return request.session.get("user")


def require_user(request: Request):
    if not get_user(request):
        return RedirectResponse("/login-page", status_code=303)

    return None


@router.get("/login")
async def login(request: Request):
    if get_user(request):
        return RedirectResponse("/", status_code=303)

    if not is_dashboard_configured():
        return RedirectResponse("/login-error", status_code=303)

    # Ochrana OAuth callbacku proti podvržení požadavku.
    state = secrets.token_urlsafe(32)
    request.session["oauth_state"] = state

    return RedirectResponse(build_login_url(state), status_code=303)


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
async def auth_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
):
    print("==== OAUTH CALLBACK ====")
    print("HAS CODE:", bool(code))
    print("ERROR:", error)
    print("========================")

    if error:
        request.session.clear()
        return RedirectResponse("/login-page", status_code=303)

    expected_state = request.session.pop("oauth_state", None)

    if not state or not expected_state or not secrets.compare_digest(state, expected_state):
        print("OAUTH ERROR: Neplatný nebo chybějící state.")
        request.session.clear()
        return RedirectResponse("/login-page", status_code=303)

    if not code:
        print("OAUTH ERROR: Chybí autorizační kód.")
        request.session.clear()
        return RedirectResponse("/login-page", status_code=303)

    if not is_dashboard_configured():
        request.session.clear()
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

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            token_response = await client.post(
                DISCORD_TOKEN_URL,
                data=data,
                headers=headers,
            )

            if token_response.status_code != 200:
                print(
                    "TOKEN ERROR:",
                    token_response.status_code,
                    token_response.text[:500],
                )
                request.session.clear()
                return RedirectResponse("/login-page", status_code=303)

            token_data = token_response.json()
            access_token = token_data.get("access_token")

            if not access_token:
                print("TOKEN ERROR: Discord nevrátil access_token.")
                request.session.clear()
                return RedirectResponse("/login-page", status_code=303)

            authorization = {"Authorization": f"Bearer {access_token}"}

            user_response = await client.get(
                f"{DISCORD_API}/users/@me",
                headers=authorization,
            )

            guilds_response = await client.get(
                f"{DISCORD_API}/users/@me/guilds",
                headers=authorization,
            )

    except httpx.HTTPError as exc:
        print("DISCORD HTTP ERROR:", repr(exc))
        request.session.clear()
        return RedirectResponse("/login-page", status_code=303)

    if user_response.status_code != 200:
        print(
            "USER ERROR:",
            user_response.status_code,
            user_response.text[:500],
        )
        request.session.clear()
        return RedirectResponse("/login-page", status_code=303)

    user = user_response.json()

    if guilds_response.status_code == 200:
        guilds = guilds_response.json()
    else:
        print(
            "GUILDS ERROR:",
            guilds_response.status_code,
            guilds_response.text[:500],
        )
        guilds = []

    manageable_guilds = []

    print("==== MANAGEABLE GUILDS ====")

    for guild in guilds:
        permissions = int(guild.get("permissions", 0))
        is_owner = bool(guild.get("owner", False))
        has_manage_guild = bool(permissions & 0x20)
        has_administrator = bool(permissions & 0x8)

        if is_owner or has_manage_guild or has_administrator:
            # Do cookie session ukládáme jen nezbytná data.
            compact_guild = {
                "id": str(guild["id"]),
                "name": guild.get("name") or "Discord Server",
                "icon": guild.get("icon"),
            }
            manageable_guilds.append(compact_guild)

            print(
                compact_guild["name"],
                compact_guild["id"],
                "owner=", is_owner,
                "manage=", has_manage_guild,
                "admin=", has_administrator,
            )

    print("===========================")

    # Před zápisem odstraníme případná stará data.
    request.session.clear()

    request.session["user"] = {
        "id": str(user["id"]),
        "username": user.get("username") or "Discord User",
        "global_name": user.get("global_name"),
        "avatar": user.get("avatar"),
    }

    request.session["guilds"] = manageable_guilds

    # Access token záměrně neukládáme do cookie session.
    session_json = json.dumps(
        dict(request.session),
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")

    print("LOGIN SUCCESS")
    print("User:", request.session["user"]["username"])
    print("Serverů:", len(manageable_guilds))
    print("SESSION DATA SIZE:", len(session_json), "bytes")
    print("===========================")

    return RedirectResponse("/", status_code=303)


@router.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login-page", status_code=303)
