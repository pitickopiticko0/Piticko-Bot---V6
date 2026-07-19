from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from config import DATABASE


load_dotenv()

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:
    psycopg = None
    dict_row = None


class MakeJPCForumStore:
    """Ukládá vazbu MakejPC produktu na Discord forum vlákno a úvodní zprávu."""

    def __init__(self, sqlite_path: Path = DATABASE) -> None:
        self.database_url = os.getenv("DATABASE_URL")
        self.sqlite_path = sqlite_path
        self._init_table()

    @property
    def using_postgres(self) -> bool:
        return bool(self.database_url)

    def connect(self):
        if self.using_postgres:
            if psycopg is None:
                raise RuntimeError(
                    "DATABASE_URL je nastavené, ale chybí psycopg. "
                    "Přidej psycopg[binary]>=3.2.0 do requirements.txt."
                )
            return psycopg.connect(
                self.database_url,
                row_factory=dict_row,
                connect_timeout=8,
            )

        self.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.sqlite_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _init_table(self) -> None:
        with self.connect() as conn:
            if self.using_postgres:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS makejpc_forum_posts (
                        product_code TEXT PRIMARY KEY,
                        forum_id BIGINT NOT NULL,
                        thread_id BIGINT NOT NULL,
                        message_id BIGINT NOT NULL,
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
            else:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS makejpc_forum_posts (
                        product_code TEXT PRIMARY KEY,
                        forum_id INTEGER NOT NULL,
                        thread_id INTEGER NOT NULL,
                        message_id INTEGER NOT NULL,
                        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
            conn.commit()

    def get(self, product_code: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            if self.using_postgres:
                row = conn.execute(
                    """
                    SELECT product_code, forum_id, thread_id, message_id
                    FROM makejpc_forum_posts
                    WHERE product_code = %s
                    """,
                    (product_code,),
                ).fetchone()
            else:
                row = conn.execute(
                    """
                    SELECT product_code, forum_id, thread_id, message_id
                    FROM makejpc_forum_posts
                    WHERE product_code = ?
                    """,
                    (product_code,),
                ).fetchone()

        return dict(row) if row else None

    def save(
        self,
        product_code: str,
        forum_id: int,
        thread_id: int,
        message_id: int,
    ) -> None:
        with self.connect() as conn:
            if self.using_postgres:
                conn.execute(
                    """
                    INSERT INTO makejpc_forum_posts
                        (product_code, forum_id, thread_id, message_id, updated_at)
                    VALUES (%s, %s, %s, %s, NOW())
                    ON CONFLICT (product_code)
                    DO UPDATE SET
                        forum_id = EXCLUDED.forum_id,
                        thread_id = EXCLUDED.thread_id,
                        message_id = EXCLUDED.message_id,
                        updated_at = NOW()
                    """,
                    (product_code, forum_id, thread_id, message_id),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO makejpc_forum_posts
                        (product_code, forum_id, thread_id, message_id, updated_at)
                    VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(product_code)
                    DO UPDATE SET
                        forum_id = excluded.forum_id,
                        thread_id = excluded.thread_id,
                        message_id = excluded.message_id,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (product_code, forum_id, thread_id, message_id),
                )
            conn.commit()

    def delete(self, product_code: str) -> None:
        with self.connect() as conn:
            placeholder = "%s" if self.using_postgres else "?"
            conn.execute(
                f"DELETE FROM makejpc_forum_posts WHERE product_code = {placeholder}",
                (product_code,),
            )
            conn.commit()


makejpc_forum_store = MakeJPCForumStore()
