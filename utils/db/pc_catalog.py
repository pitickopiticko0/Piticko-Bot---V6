"""Nastavení a vazby Discord fóra pro sledované PC sestavy."""

from typing import Any


def get_settings(database: Any, guild_id: int):
    with database.connect() as conn:
        return conn.execute(
            "SELECT * FROM pc_catalog_settings WHERE guild_id = ?", (guild_id,)
        ).fetchone()


def get_enabled_settings(database: Any):
    with database.connect() as conn:
        return conn.execute(
            """SELECT * FROM pc_catalog_settings
               WHERE enabled = 1 AND forum_channel_id IS NOT NULL
               AND (enabled_makejpc = 1 OR enabled_sestavsipocitac = 1)
               ORDER BY guild_id"""
        ).fetchall()


def save_settings(
    database: Any,
    guild_id: int,
    forum_channel_id: int | None,
    mention_role_id: int | None,
    enabled: bool,
    enabled_makejpc: bool,
    enabled_sestavsipocitac: bool,
) -> None:
    excluded = "EXCLUDED" if database.using_postgres else "excluded"
    with database.connect() as conn:
        conn.execute(
            f"""INSERT INTO pc_catalog_settings
                (guild_id, forum_channel_id, mention_role_id, enabled,
                 enabled_makejpc, enabled_sestavsipocitac, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (guild_id) DO UPDATE SET
                    forum_channel_id = {excluded}.forum_channel_id,
                    mention_role_id = {excluded}.mention_role_id,
                    enabled = {excluded}.enabled,
                    enabled_makejpc = {excluded}.enabled_makejpc,
                    enabled_sestavsipocitac = {excluded}.enabled_sestavsipocitac,
                    updated_at = {excluded}.updated_at""",
            (
                guild_id, forum_channel_id, mention_role_id, int(enabled),
                int(enabled_makejpc), int(enabled_sestavsipocitac), database.now(),
            ),
        )
        conn.commit()


def get_post(database: Any, guild_id: int, source: str, build_code: str):
    with database.connect() as conn:
        return conn.execute(
            """SELECT * FROM pc_catalog_posts
               WHERE guild_id = ? AND source = ? AND build_code = ?""",
            (guild_id, source, build_code),
        ).fetchone()


def save_post(
    database: Any, guild_id: int, source: str, build_code: str, forum_channel_id: int,
    thread_id: int, message_id: int,
) -> None:
    excluded = "EXCLUDED" if database.using_postgres else "excluded"
    with database.connect() as conn:
        conn.execute(
            f"""INSERT INTO pc_catalog_posts
                (guild_id, source, build_code, forum_channel_id, thread_id, message_id, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (guild_id, source, build_code) DO UPDATE SET
                    forum_channel_id = {excluded}.forum_channel_id,
                    thread_id = {excluded}.thread_id,
                    message_id = {excluded}.message_id,
                    updated_at = {excluded}.updated_at""",
            (guild_id, source, build_code, forum_channel_id, thread_id, message_id, database.now()),
        )
        conn.commit()


def list_posts(database: Any):
    with database.connect() as conn:
        return conn.execute("SELECT * FROM pc_catalog_posts ORDER BY updated_at DESC").fetchall()
