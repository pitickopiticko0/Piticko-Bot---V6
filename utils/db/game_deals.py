"""Databázové operace pro oznámení her zdarma a ve slevě."""

import re
from typing import Any


DEFAULT_STORE_FILTERS = "steam,epic,gog,itch,ea,ubisoft,microsoft,humble,other"
MAX_WATCHES_PER_USER = 20

SUBSCRIPTION_ROLE_COLUMNS = {
    "free": "subscription_role_free_id",
    "weekend": "subscription_role_weekend_id",
    "dlc": "subscription_role_dlc_id",
    "deal": "subscription_role_deal_id",
}


def normalize_watch_query(value: str) -> str:
    """Připraví název hry pro porovnávání bez rozdílu velikosti písmen a mezer."""
    return re.sub(r"\s+", " ", value.casefold()).strip()


def get_settings(database: Any, guild_id: int):
    with database.connect() as conn:
        return conn.execute(
            "SELECT * FROM game_deal_settings WHERE guild_id = ?", (guild_id,)
        ).fetchone()


def get_enabled(database: Any):
    with database.connect() as conn:
        return conn.execute(
            """SELECT * FROM game_deal_settings
               WHERE channel_id IS NOT NULL
                 AND (enabled_free = 1 OR enabled_weekend = 1 OR enabled_dlc = 1 OR enabled_deals = 1)
               ORDER BY guild_id"""
        ).fetchall()


def save_settings(
    database: Any,
    guild_id: int,
    channel_id: int | None,
    mention_role_id: int | None,
    enabled_free: bool,
    enabled_deals: bool,
    min_discount: int,
    enabled_weekend: bool | None = None,
    enabled_dlc: bool | None = None,
    store_filters: str | None = None,
) -> None:
    minimum = max(10, min(int(min_discount), 95))
    enabled_weekend = enabled_free if enabled_weekend is None else enabled_weekend
    enabled_dlc = enabled_free if enabled_dlc is None else enabled_dlc
    filters = store_filters or DEFAULT_STORE_FILTERS
    with database.connect() as conn:
        excluded = "EXCLUDED" if database.using_postgres else "excluded"
        conn.execute(
            f"""INSERT INTO game_deal_settings
                (guild_id, channel_id, mention_role_id, enabled_free, enabled_weekend,
                 enabled_dlc, enabled_deals, store_filters, min_discount, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (guild_id) DO UPDATE SET
                    channel_id = {excluded}.channel_id,
                    mention_role_id = {excluded}.mention_role_id,
                    enabled_free = {excluded}.enabled_free,
                    enabled_weekend = {excluded}.enabled_weekend,
                    enabled_dlc = {excluded}.enabled_dlc,
                    enabled_deals = {excluded}.enabled_deals,
                    store_filters = {excluded}.store_filters,
                    min_discount = {excluded}.min_discount,
                    updated_at = {excluded}.updated_at""",
            (
                guild_id,
                channel_id,
                mention_role_id,
                int(enabled_free),
                int(enabled_weekend),
                int(enabled_dlc),
                int(enabled_deals),
                filters,
                minimum,
                database.now(),
            ),
        )
        conn.commit()


def set_subscription_role(
    database: Any, guild_id: int, category: str, role_id: int | None
) -> bool:
    """Uloží jednu dobrovolnou odběrovou roli bez změny ostatního nastavení."""
    column = SUBSCRIPTION_ROLE_COLUMNS.get(category)
    if column is None:
        raise ValueError("Neplatný typ herního odběru.")
    with database.connect() as conn:
        cursor = conn.execute(
            f"UPDATE game_deal_settings SET {column} = ?, updated_at = ? WHERE guild_id = ?",
            (role_id, database.now(), guild_id),
        )
        conn.commit()
        return cursor.rowcount > 0


def is_seen(database: Any, guild_id: int, source: str, offer_id: str) -> bool:
    with database.connect() as conn:
        row = conn.execute(
            """SELECT 1 FROM game_deal_seen
               WHERE guild_id = ? AND source = ? AND offer_id = ?""",
            (guild_id, source, offer_id),
        ).fetchone()
        return row is not None


def mark_seen(database: Any, guild_id: int, source: str, offer_id: str) -> None:
    with database.connect() as conn:
        conn.execute(
            """INSERT INTO game_deal_seen (guild_id, source, offer_id, seen_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT (guild_id, source, offer_id) DO NOTHING""",
            (guild_id, source, offer_id, database.now()),
        )
        conn.commit()


def is_initialized(database: Any, guild_id: int, kind: str) -> bool:
    column = "initialized_free" if kind == "free" else "initialized_deals"
    with database.connect() as conn:
        row = conn.execute(
            f"SELECT {column} AS value FROM game_deal_settings WHERE guild_id = ?",
            (guild_id,),
        ).fetchone()
        return bool(row and row["value"])


def set_initialized(database: Any, guild_id: int, kind: str) -> None:
    column = "initialized_free" if kind == "free" else "initialized_deals"
    with database.connect() as conn:
        conn.execute(
            f"UPDATE game_deal_settings SET {column} = 1, updated_at = ? WHERE guild_id = ?",
            (database.now(), guild_id),
        )
        conn.commit()


def count_seen(database: Any, guild_id: int) -> int:
    with database.connect() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS count FROM game_deal_seen WHERE guild_id = ?",
            (guild_id,),
        ).fetchone()
        return int(row["count"] if row else 0)


def list_watches(database: Any, guild_id: int, user_id: int | None = None):
    query = "SELECT * FROM game_deal_watches WHERE guild_id = ?"
    params: tuple = (guild_id,)
    if user_id is not None:
        query += " AND user_id = ?"
        params = (guild_id, user_id)
    query += " ORDER BY created_at ASC"
    with database.connect() as conn:
        return conn.execute(query, params).fetchall()


def add_watch(database: Any, guild_id: int, user_id: int, query: str) -> bool:
    normalized = normalize_watch_query(query)
    with database.connect() as conn:
        existing = conn.execute(
            """SELECT 1 FROM game_deal_watches
               WHERE guild_id = ? AND user_id = ? AND normalized_query = ?""",
            (guild_id, user_id, normalized),
        ).fetchone()
        if existing is not None:
            return False
        count = conn.execute(
            "SELECT COUNT(*) AS count FROM game_deal_watches WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        ).fetchone()
        if int(count["count"] if count else 0) >= MAX_WATCHES_PER_USER:
            raise ValueError(f"Limit je {MAX_WATCHES_PER_USER} sledovaných her.")
        conn.execute(
            """INSERT INTO game_deal_watches
               (guild_id, user_id, query, normalized_query, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (guild_id, user_id, query, normalized, database.now()),
        )
        conn.commit()
        return True


def remove_watch(database: Any, guild_id: int, user_id: int, query: str) -> bool:
    normalized = normalize_watch_query(query)
    with database.connect() as conn:
        cursor = conn.execute(
            """DELETE FROM game_deal_watches
               WHERE guild_id = ? AND user_id = ? AND normalized_query = ?""",
            (guild_id, user_id, normalized),
        )
        conn.commit()
        return cursor.rowcount > 0


def watch_was_notified(
    database: Any, guild_id: int, user_id: int, source: str, offer_id: str
) -> bool:
    with database.connect() as conn:
        row = conn.execute(
            """SELECT 1 FROM game_deal_watch_notifications
               WHERE guild_id = ? AND user_id = ? AND source = ? AND offer_id = ?""",
            (guild_id, user_id, source, offer_id),
        ).fetchone()
        return row is not None


def mark_watch_notified(
    database: Any, guild_id: int, user_id: int, source: str, offer_id: str
) -> None:
    with database.connect() as conn:
        conn.execute(
            """INSERT INTO game_deal_watch_notifications
               (guild_id, user_id, source, offer_id, notified_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT (guild_id, user_id, source, offer_id) DO NOTHING""",
            (guild_id, user_id, source, offer_id, database.now()),
        )
        conn.commit()
