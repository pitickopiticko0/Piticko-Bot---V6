from typing import Optional

from fastapi import APIRouter, Form

from utils.database import db
from utils.youtube_api import YouTubeAPIError, youtube_api


router = APIRouter(prefix="/api/youtube", tags=["youtube"])


def serialize_row(row) -> dict:
    return {
        "guild_id": row["guild_id"],
        "youtube_channel_id": row["youtube_channel_id"],
        "youtube_name": row["youtube_name"],
        "youtube_url": row["youtube_url"],
        "discord_channel_id": row["discord_channel_id"],
        "mention_role_id": row["mention_role_id"],
        "last_video_id": row["last_video_id"],
        "enabled": bool(row["enabled"]),
    }


@router.get("")
async def list_youtube_subscriptions():
    rows = db.get_enabled_subscriptions()

    return {
        "items": [serialize_row(row) for row in rows],
        "count": len(rows),
    }


@router.get("/all")
async def list_all_youtube_subscriptions():
    with db.connect() as conn:
        rows = conn.execute("""
            SELECT
                s.*,
                y.youtube_name,
                y.youtube_url
            FROM subscriptions s
            JOIN youtube_channels y
                ON y.youtube_channel_id = s.youtube_channel_id
            ORDER BY y.youtube_name ASC
        """).fetchall()

    return {
        "items": [serialize_row(row) for row in rows],
        "count": len(rows),
    }


@router.post("/add")
async def add_youtube_subscription(
    guild_id: int = Form(...),
    guild_name: str = Form("Dashboard"),
    youtube_url: str = Form(...),
    discord_channel_id: int = Form(...),
    mention_role_id: Optional[int] = Form(None),
):
    try:
        yt_channel = await youtube_api.resolve_channel(youtube_url)

        db.add_guild(
            guild_id=guild_id,
            guild_name=guild_name or "Dashboard",
        )

        db.add_youtube_channel(
            channel_id=yt_channel.id,
            name=yt_channel.title,
            url=yt_channel.url,
        )

        db.add_subscription(
            guild_id=guild_id,
            youtube_channel_id=yt_channel.id,
            discord_channel_id=discord_channel_id,
            mention_role_id=mention_role_id,
        )

        return {
            "ok": True,
            "message": "Odběr byl přidán.",
            "channel": {
                "id": yt_channel.id,
                "title": yt_channel.title,
                "url": yt_channel.url,
            },
        }

    except YouTubeAPIError as e:
        return {
            "ok": False,
            "error": str(e),
        }


@router.post("/remove")
async def remove_youtube_subscription(
    guild_id: int = Form(...),
    youtube_channel_id: str = Form(...),
):
    removed = db.remove_subscription(
        guild_id=guild_id,
        youtube_channel_id=youtube_channel_id,
    )

    return {
        "ok": removed,
        "message": "Odběr byl odebrán." if removed else "Odběr nebyl nalezen.",
    }


@router.post("/pause")
async def pause_youtube_subscription(
    guild_id: int = Form(...),
    youtube_channel_id: str = Form(...),
):
    db.pause_subscription(
        guild_id=guild_id,
        youtube_channel_id=youtube_channel_id,
    )

    return {
        "ok": True,
        "message": "Odběr byl pozastaven.",
    }


@router.post("/resume")
async def resume_youtube_subscription(
    guild_id: int = Form(...),
    youtube_channel_id: str = Form(...),
):
    db.resume_subscription(
        guild_id=guild_id,
        youtube_channel_id=youtube_channel_id,
    )

    return {
        "ok": True,
        "message": "Odběr byl znovu zapnut.",
    }
