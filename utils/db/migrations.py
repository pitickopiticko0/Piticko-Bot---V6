"""Vytváření tabulek a bezpečné migrace podporovaných databází."""

from typing import Any


POSTGRES_TABLES = (
    """CREATE TABLE IF NOT EXISTS guilds (
        guild_id BIGINT PRIMARY KEY, guild_name TEXT NOT NULL,
        created_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS youtube_channels (
        youtube_channel_id TEXT PRIMARY KEY, youtube_name TEXT NOT NULL,
        youtube_url TEXT NOT NULL, created_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS subscriptions (
        id BIGSERIAL PRIMARY KEY, guild_id BIGINT NOT NULL,
        youtube_channel_id TEXT NOT NULL, discord_channel_id BIGINT NOT NULL,
        mention_role_id BIGINT, last_video_id TEXT,
        enabled INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL,
        UNIQUE(guild_id, youtube_channel_id)
    )""",
    """CREATE TABLE IF NOT EXISTS videos (
        video_id TEXT PRIMARY KEY, youtube_channel_id TEXT NOT NULL,
        title TEXT NOT NULL, url TEXT NOT NULL, published_at TEXT,
        announced_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS youtube_announcements (
        guild_id BIGINT NOT NULL, youtube_channel_id TEXT NOT NULL,
        video_id TEXT NOT NULL, announced_at TEXT NOT NULL,
        PRIMARY KEY (guild_id, youtube_channel_id, video_id)
    )""",
    """CREATE TABLE IF NOT EXISTS welcome_settings (
        guild_id BIGINT PRIMARY KEY, channel_id BIGINT, role_id BIGINT,
        enabled INTEGER NOT NULL DEFAULT 0, message TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS guild_settings (
        guild_id BIGINT PRIMARY KEY, language TEXT NOT NULL DEFAULT 'cs',
        timezone TEXT NOT NULL DEFAULT 'Europe/Prague',
        command_channel_id BIGINT, updated_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS makejpc_products (
        product_code TEXT PRIMARY KEY, name TEXT NOT NULL, price TEXT,
        availability TEXT, product_url TEXT NOT NULL, image_url TEXT,
        announced INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS autorole_settings (
        guild_id BIGINT PRIMARY KEY, role_id BIGINT NOT NULL,
        enabled INTEGER NOT NULL DEFAULT 1, updated_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS modlog_settings (
        guild_id BIGINT PRIMARY KEY, channel_id BIGINT NOT NULL,
        enabled INTEGER NOT NULL DEFAULT 1,
        log_members INTEGER NOT NULL DEFAULT 1,
        log_messages INTEGER NOT NULL DEFAULT 1,
        log_voice INTEGER NOT NULL DEFAULT 1,
        log_channels INTEGER NOT NULL DEFAULT 1,
        log_bans INTEGER NOT NULL DEFAULT 1,
        updated_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS antispam_settings (
        guild_id BIGINT PRIMARY KEY, enabled INTEGER NOT NULL DEFAULT 1,
        max_messages INTEGER NOT NULL DEFAULT 6,
        interval_seconds INTEGER NOT NULL DEFAULT 8,
        duplicate_limit INTEGER NOT NULL DEFAULT 3,
        mention_limit INTEGER NOT NULL DEFAULT 5,
        timeout_minutes INTEGER NOT NULL DEFAULT 10,
        delete_messages INTEGER NOT NULL DEFAULT 1,
        updated_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS ticket_settings (
        guild_id BIGINT PRIMARY KEY, panel_channel_id BIGINT NOT NULL,
        category_id BIGINT NOT NULL, support_role_id BIGINT NOT NULL,
        log_channel_id BIGINT, enabled INTEGER NOT NULL DEFAULT 1,
        updated_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS tickets (
        id BIGSERIAL PRIMARY KEY, guild_id BIGINT NOT NULL,
        channel_id BIGINT UNIQUE NOT NULL, user_id BIGINT NOT NULL,
        subject TEXT NOT NULL, description TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'open', claimed_by BIGINT,
        created_at TEXT NOT NULL, closed_at TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS giveaways (
        id BIGSERIAL PRIMARY KEY, guild_id BIGINT NOT NULL,
        channel_id BIGINT NOT NULL, message_id BIGINT, host_id BIGINT NOT NULL,
        prize TEXT NOT NULL, description TEXT NOT NULL,
        winner_count INTEGER NOT NULL DEFAULT 1, end_at TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'active', created_at TEXT NOT NULL,
        ended_at TEXT, winners_text TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS giveaway_entries (
        id BIGSERIAL PRIMARY KEY, giveaway_id BIGINT NOT NULL,
        user_id BIGINT NOT NULL, joined_at TEXT NOT NULL,
        UNIQUE(giveaway_id, user_id)
    )""",
    """CREATE TABLE IF NOT EXISTS moderation_warnings (id BIGSERIAL PRIMARY KEY, guild_id BIGINT NOT NULL, user_id BIGINT NOT NULL, moderator_id BIGINT NOT NULL, reason TEXT NOT NULL, created_at TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS moderation_actions (id BIGSERIAL PRIMARY KEY, guild_id BIGINT NOT NULL, user_id BIGINT NOT NULL, moderator_id BIGINT NOT NULL, action TEXT NOT NULL, reason TEXT NOT NULL, duration_minutes INTEGER, created_at TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS moderation_notes (id BIGSERIAL PRIMARY KEY, guild_id BIGINT NOT NULL, user_id BIGINT NOT NULL, moderator_id BIGINT NOT NULL, note TEXT NOT NULL, created_at TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS moderation_settings (guild_id BIGINT PRIMARY KEY, auto_punishments INTEGER NOT NULL DEFAULT 0, updated_at TEXT NOT NULL)""",
)


SQLITE_TABLES = (
    """CREATE TABLE IF NOT EXISTS guilds (
        guild_id INTEGER PRIMARY KEY, guild_name TEXT NOT NULL,
        created_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS youtube_channels (
        youtube_channel_id TEXT PRIMARY KEY, youtube_name TEXT NOT NULL,
        youtube_url TEXT NOT NULL, created_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS subscriptions (
        id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER NOT NULL,
        youtube_channel_id TEXT NOT NULL, discord_channel_id INTEGER NOT NULL,
        mention_role_id INTEGER, last_video_id TEXT,
        enabled INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL,
        UNIQUE(guild_id, youtube_channel_id)
    )""",
    """CREATE TABLE IF NOT EXISTS videos (
        video_id TEXT PRIMARY KEY, youtube_channel_id TEXT NOT NULL,
        title TEXT NOT NULL, url TEXT NOT NULL, published_at TEXT,
        announced_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS youtube_announcements (
        guild_id INTEGER NOT NULL, youtube_channel_id TEXT NOT NULL,
        video_id TEXT NOT NULL, announced_at TEXT NOT NULL,
        PRIMARY KEY (guild_id, youtube_channel_id, video_id)
    )""",
    """CREATE TABLE IF NOT EXISTS welcome_settings (
        guild_id INTEGER PRIMARY KEY, channel_id INTEGER, role_id INTEGER,
        enabled INTEGER NOT NULL DEFAULT 0, message TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS guild_settings (
        guild_id INTEGER PRIMARY KEY, language TEXT NOT NULL DEFAULT 'cs',
        timezone TEXT NOT NULL DEFAULT 'Europe/Prague',
        command_channel_id INTEGER, updated_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS makejpc_products (
        product_code TEXT PRIMARY KEY, name TEXT NOT NULL, price TEXT,
        availability TEXT, product_url TEXT NOT NULL, image_url TEXT,
        announced INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS autorole_settings (
        guild_id INTEGER PRIMARY KEY, role_id INTEGER NOT NULL,
        enabled INTEGER NOT NULL DEFAULT 1, updated_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS modlog_settings (
        guild_id INTEGER PRIMARY KEY, channel_id INTEGER NOT NULL,
        enabled INTEGER NOT NULL DEFAULT 1,
        log_members INTEGER NOT NULL DEFAULT 1,
        log_messages INTEGER NOT NULL DEFAULT 1,
        log_voice INTEGER NOT NULL DEFAULT 1,
        log_channels INTEGER NOT NULL DEFAULT 1,
        log_bans INTEGER NOT NULL DEFAULT 1,
        updated_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS antispam_settings (
        guild_id INTEGER PRIMARY KEY, enabled INTEGER NOT NULL DEFAULT 1,
        max_messages INTEGER NOT NULL DEFAULT 6,
        interval_seconds INTEGER NOT NULL DEFAULT 8,
        duplicate_limit INTEGER NOT NULL DEFAULT 3,
        mention_limit INTEGER NOT NULL DEFAULT 5,
        timeout_minutes INTEGER NOT NULL DEFAULT 10,
        delete_messages INTEGER NOT NULL DEFAULT 1,
        updated_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS ticket_settings (
        guild_id INTEGER PRIMARY KEY, panel_channel_id INTEGER NOT NULL,
        category_id INTEGER NOT NULL, support_role_id INTEGER NOT NULL,
        log_channel_id INTEGER, enabled INTEGER NOT NULL DEFAULT 1,
        updated_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS tickets (
        id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER NOT NULL,
        channel_id INTEGER UNIQUE NOT NULL, user_id INTEGER NOT NULL,
        subject TEXT NOT NULL, description TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'open', claimed_by INTEGER,
        created_at TEXT NOT NULL, closed_at TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS giveaways (
        id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER NOT NULL,
        channel_id INTEGER NOT NULL, message_id INTEGER, host_id INTEGER NOT NULL,
        prize TEXT NOT NULL, description TEXT NOT NULL,
        winner_count INTEGER NOT NULL DEFAULT 1, end_at TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'active', created_at TEXT NOT NULL,
        ended_at TEXT, winners_text TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS giveaway_entries (
        id INTEGER PRIMARY KEY AUTOINCREMENT, giveaway_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL, joined_at TEXT NOT NULL,
        UNIQUE(giveaway_id, user_id)
    )""",
    """CREATE TABLE IF NOT EXISTS moderation_warnings (id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER NOT NULL, user_id INTEGER NOT NULL, moderator_id INTEGER NOT NULL, reason TEXT NOT NULL, created_at TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS moderation_actions (id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER NOT NULL, user_id INTEGER NOT NULL, moderator_id INTEGER NOT NULL, action TEXT NOT NULL, reason TEXT NOT NULL, duration_minutes INTEGER, created_at TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS moderation_notes (id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER NOT NULL, user_id INTEGER NOT NULL, moderator_id INTEGER NOT NULL, note TEXT NOT NULL, created_at TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS moderation_settings (guild_id INTEGER PRIMARY KEY, auto_punishments INTEGER NOT NULL DEFAULT 0, updated_at TEXT NOT NULL)""",
)


POSTGRES_MIGRATIONS = (
    "ALTER TABLE welcome_settings ADD COLUMN IF NOT EXISTS embed_title TEXT NOT NULL DEFAULT 'Vítej!'",
    "ALTER TABLE welcome_settings ADD COLUMN IF NOT EXISTS embed_color TEXT NOT NULL DEFAULT '#5865F2'",
    "ALTER TABLE welcome_settings ADD COLUMN IF NOT EXISTS dm_enabled INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS custom_message TEXT NOT NULL DEFAULT '📺 Nové video: {title}\n{url}'",
    "ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS check_interval INTEGER NOT NULL DEFAULT 300",
)


SQLITE_MIGRATIONS = {
    "welcome_settings": {
        "embed_title": "ALTER TABLE welcome_settings ADD COLUMN embed_title TEXT NOT NULL DEFAULT 'Vítej!'",
        "embed_color": "ALTER TABLE welcome_settings ADD COLUMN embed_color TEXT NOT NULL DEFAULT '#5865F2'",
        "dm_enabled": "ALTER TABLE welcome_settings ADD COLUMN dm_enabled INTEGER NOT NULL DEFAULT 0",
    },
    "subscriptions": {
        "custom_message": "ALTER TABLE subscriptions ADD COLUMN custom_message TEXT NOT NULL DEFAULT '📺 Nové video: {title}\n{url}'",
        "check_interval": "ALTER TABLE subscriptions ADD COLUMN check_interval INTEGER NOT NULL DEFAULT 300",
    },
}


def initialize(database: Any) -> None:
    if database.using_postgres:
        _initialize_postgres(database)
    else:
        _initialize_sqlite(database)


def _initialize_postgres(database: Any) -> None:
    with database.connect() as conn:
        for statement in POSTGRES_TABLES:
            conn.execute(statement)
        for statement in POSTGRES_MIGRATIONS:
            conn.execute(statement)
        conn.commit()


def _initialize_sqlite(database: Any) -> None:
    with database.connect() as conn:
        for statement in SQLITE_TABLES:
            conn.execute(statement)

        # PRAGMA je záměrně pouze ve SQLite větvi.
        for table, migrations in SQLITE_MIGRATIONS.items():
            columns = {
                row[1]
                for row in conn.execute(
                    f"PRAGMA table_info({table})"
                ).fetchall()
            }
            for column, statement in migrations.items():
                if column not in columns:
                    conn.execute(statement)
        conn.commit()
