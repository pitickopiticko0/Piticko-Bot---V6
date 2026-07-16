from fastapi import APIRouter

from config import VERSION
from utils.database import db


router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
async def api_health():
    try:
        db.stats()
        database = "ok"
    except Exception:
        database = "error"

    return {
        "status": "ok" if database == "ok" else "error",
        "version": VERSION,
        "database": database,
    }
