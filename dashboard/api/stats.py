from fastapi import APIRouter

from config import VERSION
from utils.database import db


router = APIRouter(prefix="/api", tags=["stats"])


@router.get("/stats")
async def api_stats():
    data = db.stats()

    return {
        "version": VERSION,
        "guilds": data["guilds"],
        "youtube_channels": data["youtube_channels"],
        "subscriptions": data["subscriptions"],
        "videos": data["videos"],
    }
