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
               WHERE enabled = 1 AND (
                    (enabled_sestavsipocitac = 1 AND forum_channel_id IS NOT NULL)
                    OR (enabled_buildz = 1 AND buildz_forum_channel_id IS NOT NULL)
               )
               ORDER BY guild_id"""
        ).fetchall()


def save_settings(
    database: Any,
    guild_id: int,
    forum_channel_id: int | None,
    mention_role_id: int | None,
    buildz_forum_channel_id: int | None,
    buildz_mention_role_id: int | None,
    enabled: bool,
    enabled_makejpc: bool,
    enabled_sestavsipocitac: bool,
    enabled_buildz: bool,
) -> None:
    excluded = "EXCLUDED" if database.using_postgres else "excluded"
    with database.connect() as conn:
        conn.execute(
            f"""INSERT INTO pc_catalog_settings
                (guild_id, forum_channel_id, mention_role_id,
                 buildz_forum_channel_id, buildz_mention_role_id, enabled,
                 enabled_makejpc, enabled_sestavsipocitac, enabled_buildz, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (guild_id) DO UPDATE SET
                    forum_channel_id = {excluded}.forum_channel_id,
                    mention_role_id = {excluded}.mention_role_id,
                    buildz_forum_channel_id = {excluded}.buildz_forum_channel_id,
                    buildz_mention_role_id = {excluded}.buildz_mention_role_id,
                    enabled = {excluded}.enabled,
                    enabled_makejpc = {excluded}.enabled_makejpc,
                    enabled_sestavsipocitac = {excluded}.enabled_sestavsipocitac,
                    enabled_buildz = {excluded}.enabled_buildz,
                    updated_at = {excluded}.updated_at""",
            (
                guild_id, forum_channel_id, mention_role_id,
                buildz_forum_channel_id, buildz_mention_role_id, int(enabled),
                int(enabled_makejpc), int(enabled_sestavsipocitac), int(enabled_buildz), database.now(),
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


def list_posts_for_source(database: Any, guild_id: int, source: str):
    with database.connect() as conn:
        return conn.execute(
            """SELECT * FROM pc_catalog_posts
               WHERE guild_id = ? AND source = ?""",
            (guild_id, source),
        ).fetchall()


def delete_post(database: Any, guild_id: int, source: str, build_code: str) -> None:
    with database.connect() as conn:
        conn.execute(
            """DELETE FROM pc_catalog_posts
               WHERE guild_id = ? AND source = ? AND build_code = ?""",
            (guild_id, source, build_code),
        )
        conn.commit()


def get_seen_codes(database: Any, guild_id: int, source: str) -> set[str]:
    with database.connect() as conn:
        rows = conn.execute(
            """SELECT build_code FROM pc_catalog_seen_builds
               WHERE guild_id = ? AND source = ?""",
            (guild_id, source),
        ).fetchall()
    return {str(row["build_code"]) for row in rows}


def add_seen_codes(
    database: Any, guild_id: int, source: str, build_codes: set[str]
) -> None:
    if not build_codes:
        return
    excluded = "EXCLUDED" if database.using_postgres else "excluded"
    with database.connect() as conn:
        for build_code in build_codes:
            conn.execute(
                f"""INSERT INTO pc_catalog_seen_builds
                    (guild_id, source, build_code, seen_at)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT (guild_id, source, build_code) DO UPDATE SET
                        seen_at = {excluded}.seen_at""",
                (guild_id, source, build_code, database.now()),
            )
        conn.commit()


def request_refresh(database: Any, guild_id: int) -> None:
    excluded = "EXCLUDED" if database.using_postgres else "excluded"
    with database.connect() as conn:
        conn.execute(
            f"""INSERT INTO pc_catalog_refresh_requests (guild_id, requested_at)
                VALUES (?, ?)
                ON CONFLICT (guild_id) DO UPDATE SET requested_at = {excluded}.requested_at""",
            (guild_id, database.now()),
        )
        conn.commit()


def list_refresh_requests(database: Any):
    with database.connect() as conn:
        return conn.execute(
            "SELECT guild_id FROM pc_catalog_refresh_requests ORDER BY requested_at"
        ).fetchall()


def clear_refresh_request(database: Any, guild_id: int) -> None:
    with database.connect() as conn:
        conn.execute("DELETE FROM pc_catalog_refresh_requests WHERE guild_id = ?", (guild_id,))
        conn.commit()
