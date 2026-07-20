import asyncio
import json
import os
import sqlite3
from copy import deepcopy
from pathlib import Path
from typing import Any


DEFAULT_SETTINGS: dict[str, Any] = {
    "general": {
        "language": "cs",
        "timezone": "Europe/Prague",
        "command_channel_id": "",
    },
    "welcome": {
        "enabled": False,
        "channel_id": "",
        "message": "Vítej {mention} na serveru {server}!",
        "embed_title": "Vítej!",
        "embed_color": "#5865F2",
        "dm_enabled": False,
    },
    "youtube": {
        "enabled": False,
        "channel_id": "",
        "youtube_channel_id": "",
        "custom_message": "📺 Nové video: {title}\n{url}",
        "mention_role_id": "",
        "check_interval": 300,
    },
}


class DashboardStorage:
    def __init__(self) -> None:
        self.database_url = os.getenv("DATABASE_URL", "").strip()
        self.sqlite_path = Path(
            os.getenv(
                "DASHBOARD_SQLITE_PATH",
                Path(__file__).resolve().parent / "data" / "dashboard.sqlite3",
            )
        )
        self.backend_name = "postgresql" if self.database_url else "sqlite"

    async def initialize(self) -> None:
        if self.database_url:
            await asyncio.to_thread(self._pg_initialize)
        else:
            await asyncio.to_thread(self._sqlite_initialize)

    async def get_settings(self, guild_id: str) -> dict[str, Any]:
        if self.database_url:
            raw = await asyncio.to_thread(self._pg_get, guild_id)
        else:
            raw = await asyncio.to_thread(self._sqlite_get, guild_id)

        settings = deepcopy(DEFAULT_SETTINGS)
        if isinstance(raw, dict):
            for module, values in raw.items():
                if module in settings and isinstance(values, dict):
                    settings[module].update(values)
                else:
                    settings[module] = values
        return settings

    async def update_module(
        self,
        guild_id: str,
        module: str,
        values: dict[str, Any],
    ) -> None:
        settings = await self.get_settings(guild_id)
        settings[module] = values

        if self.database_url:
            await asyncio.to_thread(self._pg_save, guild_id, settings)
        else:
            await asyncio.to_thread(self._sqlite_save, guild_id, settings)

    async def count_configured_guilds(self, guild_ids: list[str]) -> int:
        if not guild_ids:
            return 0
        if self.database_url:
            return await asyncio.to_thread(self._pg_count, guild_ids)
        return await asyncio.to_thread(self._sqlite_count, guild_ids)

    def _sqlite_connect(self) -> sqlite3.Connection:
        self.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.sqlite_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _sqlite_initialize(self) -> None:
        with self._sqlite_connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS dashboard_guild_settings (
                    guild_id TEXT PRIMARY KEY,
                    settings_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

    def _sqlite_get(self, guild_id: str) -> dict[str, Any] | None:
        with self._sqlite_connect() as conn:
            row = conn.execute(
                "SELECT settings_json FROM dashboard_guild_settings WHERE guild_id = ?",
                (str(guild_id),),
            ).fetchone()
        if not row:
            return None
        return json.loads(row["settings_json"])

    def _sqlite_save(self, guild_id: str, settings: dict[str, Any]) -> None:
        payload = json.dumps(settings, ensure_ascii=False)
        with self._sqlite_connect() as conn:
            conn.execute(
                """
                INSERT INTO dashboard_guild_settings
                    (guild_id, settings_json, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(guild_id) DO UPDATE SET
                    settings_json = excluded.settings_json,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (str(guild_id), payload),
            )

    def _sqlite_count(self, guild_ids: list[str]) -> int:
        placeholders = ",".join("?" for _ in guild_ids)
        with self._sqlite_connect() as conn:
            row = conn.execute(
                f"""
                SELECT COUNT(*) AS total
                FROM dashboard_guild_settings
                WHERE guild_id IN ({placeholders})
                """,
                guild_ids,
            ).fetchone()
        return int(row["total"])

    def _pg_connect(self):
        try:
            import psycopg
            return psycopg.connect(self.database_url)
        except ImportError:
            import psycopg2
            return psycopg2.connect(self.database_url)

    def _pg_initialize(self) -> None:
        with self._pg_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS dashboard_guild_settings (
                        guild_id TEXT PRIMARY KEY,
                        settings_json JSONB NOT NULL,
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
            conn.commit()

    def _pg_get(self, guild_id: str) -> dict[str, Any] | None:
        with self._pg_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT settings_json
                    FROM dashboard_guild_settings
                    WHERE guild_id = %s
                    """,
                    (str(guild_id),),
                )
                row = cur.fetchone()

        if not row:
            return None

        value = row[0]
        if isinstance(value, str):
            return json.loads(value)
        return value

    def _pg_save(self, guild_id: str, settings: dict[str, Any]) -> None:
        payload = json.dumps(settings, ensure_ascii=False)
        with self._pg_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO dashboard_guild_settings
                        (guild_id, settings_json, updated_at)
                    VALUES (%s, %s::jsonb, NOW())
                    ON CONFLICT(guild_id) DO UPDATE SET
                        settings_json = EXCLUDED.settings_json,
                        updated_at = NOW()
                    """,
                    (str(guild_id), payload),
                )
            conn.commit()

    def _pg_count(self, guild_ids: list[str]) -> int:
        with self._pg_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT COUNT(*)
                    FROM dashboard_guild_settings
                    WHERE guild_id = ANY(%s)
                    """,
                    (guild_ids,),
                )
                row = cur.fetchone()
        return int(row[0])
