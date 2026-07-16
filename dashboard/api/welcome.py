from fastapi import APIRouter

from utils.database import db


router = APIRouter(prefix="/api/welcome", tags=["welcome"])


def serialize_row(row) -> dict:
    return {
        "guild_id": row["guild_id"],
        "guild_name": row["guild_name"],
        "channel_id": row["channel_id"],
        "role_id": row["role_id"],
        "enabled": bool(row["enabled"]),
        "message": row["message"],
        "updated_at": row["updated_at"],
    }


@router.get("")
async def list_welcome_settings():
    with db.connect() as conn:
        rows = conn.execute("""
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
            ORDER BY g.guild_name ASC
        """).fetchall()

    return {
        "items": [serialize_row(row) for row in rows],
        "count": len(rows),
    }
