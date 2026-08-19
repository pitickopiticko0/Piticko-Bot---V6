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
    """CREATE TABLE IF NOT EXISTS service_health (
        service TEXT PRIMARY KEY, status TEXT NOT NULL,
        message TEXT, checked_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS twitch_subscriptions (
        id BIGSERIAL PRIMARY KEY, guild_id BIGINT NOT NULL,
        twitch_user_id TEXT NOT NULL, streamer_login TEXT NOT NULL,
        streamer_name TEXT NOT NULL, discord_channel_id BIGINT NOT NULL,
        mention_role_id BIGINT, profile_image_url TEXT, last_stream_id TEXT,
        is_live INTEGER NOT NULL DEFAULT 0, enabled INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL, UNIQUE(guild_id, twitch_user_id)
    )""",
    """CREATE TABLE IF NOT EXISTS kick_subscriptions (
        id BIGSERIAL PRIMARY KEY, guild_id BIGINT NOT NULL,
        kick_user_id TEXT NOT NULL, streamer_slug TEXT NOT NULL,
        discord_channel_id BIGINT NOT NULL, mention_role_id BIGINT,
        is_live INTEGER NOT NULL DEFAULT 0, enabled INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL, UNIQUE(guild_id, kick_user_id)
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
        ignored_channel_ids TEXT NOT NULL DEFAULT '',
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
    """CREATE TABLE IF NOT EXISTS pc_advice_settings (
        guild_id BIGINT PRIMARY KEY, panel_channel_id BIGINT NOT NULL,
        category_id BIGINT NOT NULL, advisor_role_id BIGINT NOT NULL,
        log_channel_id BIGINT, mode TEXT NOT NULL DEFAULT 'private',
        forum_channel_id BIGINT, enabled INTEGER NOT NULL DEFAULT 1,
        reminders_enabled INTEGER NOT NULL DEFAULT 0,
        reminder_days INTEGER NOT NULL DEFAULT 3,
        updated_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS pc_advice_requests (
        id BIGSERIAL PRIMARY KEY, guild_id BIGINT NOT NULL,
        channel_id BIGINT UNIQUE NOT NULL, user_id BIGINT NOT NULL,
        request_type TEXT NOT NULL, answers TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'open', claimed_by BIGINT,
        created_at TEXT NOT NULL, resolved_at TEXT, closed_at TEXT,
        last_reminded_message_id BIGINT
    )""",
    """CREATE TABLE IF NOT EXISTS abi_rank_settings (
        guild_id BIGINT PRIMARY KEY, review_channel_id BIGINT NOT NULL,
        reviewer_role_id BIGINT NOT NULL, rookie_role_id BIGINT,
        vanguard_role_id BIGINT, elite_role_id BIGINT, expert_role_id BIGINT,
        master_role_id BIGINT, ace_role_id BIGINT, hero_role_id BIGINT,
        legend_role_id BIGINT,
        enabled INTEGER NOT NULL DEFAULT 1, updated_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS abi_rank_requests (
        id BIGSERIAL PRIMARY KEY, guild_id BIGINT NOT NULL, user_id BIGINT NOT NULL,
        game_name TEXT NOT NULL, game_uid TEXT NOT NULL, rank_key TEXT NOT NULL,
        division TEXT, screenshot_url TEXT NOT NULL, review_message_id BIGINT,
        status TEXT NOT NULL DEFAULT 'pending', reviewer_id BIGINT,
        review_reason TEXT, created_at TEXT NOT NULL, reviewed_at TEXT
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
    """CREATE TABLE IF NOT EXISTS pc_build_challenges (
        id BIGSERIAL PRIMARY KEY, guild_id BIGINT NOT NULL, channel_id BIGINT NOT NULL,
        message_id BIGINT, host_id BIGINT NOT NULL, budget INTEGER NOT NULL,
        purpose TEXT NOT NULL, end_at TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'active', created_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS pc_build_entries (
        id BIGSERIAL PRIMARY KEY, challenge_id BIGINT NOT NULL, user_id BIGINT NOT NULL,
        cpu TEXT NOT NULL, gpu TEXT NOT NULL, other_parts TEXT NOT NULL,
        total_price INTEGER NOT NULL, reasoning TEXT NOT NULL, created_at TEXT NOT NULL,
        UNIQUE(challenge_id, user_id)
    )""",
    """CREATE TABLE IF NOT EXISTS pc_build_votes (
        challenge_id BIGINT NOT NULL, entry_id BIGINT NOT NULL,
        user_id BIGINT NOT NULL, created_at TEXT NOT NULL,
        PRIMARY KEY (challenge_id, user_id)
    )""",
    """CREATE TABLE IF NOT EXISTS moderation_warnings (id BIGSERIAL PRIMARY KEY, guild_id BIGINT NOT NULL, user_id BIGINT NOT NULL, moderator_id BIGINT NOT NULL, reason TEXT NOT NULL, created_at TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS moderation_actions (id BIGSERIAL PRIMARY KEY, guild_id BIGINT NOT NULL, user_id BIGINT NOT NULL, moderator_id BIGINT NOT NULL, action TEXT NOT NULL, reason TEXT NOT NULL, duration_minutes INTEGER, created_at TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS moderation_notes (id BIGSERIAL PRIMARY KEY, guild_id BIGINT NOT NULL, user_id BIGINT NOT NULL, moderator_id BIGINT NOT NULL, note TEXT NOT NULL, created_at TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS moderation_settings (guild_id BIGINT PRIMARY KEY, auto_punishments INTEGER NOT NULL DEFAULT 0, updated_at TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS sheep_game_settings (
        guild_id BIGINT PRIMARY KEY, channel_id BIGINT,
        enabled INTEGER NOT NULL DEFAULT 0,
        current_count INTEGER NOT NULL DEFAULT 0,
        record_count INTEGER NOT NULL DEFAULT 0,
        last_user_id BIGINT, total_valid_counts BIGINT NOT NULL DEFAULT 0,
        updated_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS sheep_game_players (
        guild_id BIGINT NOT NULL, user_id BIGINT NOT NULL,
        valid_counts BIGINT NOT NULL DEFAULT 0,
        chains_broken INTEGER NOT NULL DEFAULT 0,
        updated_at TEXT NOT NULL,
        PRIMARY KEY (guild_id, user_id)
    )""",
    """CREATE TABLE IF NOT EXISTS game_deal_settings (
        guild_id BIGINT PRIMARY KEY, channel_id BIGINT, mention_role_id BIGINT,
        enabled_free INTEGER NOT NULL DEFAULT 1,
        enabled_deals INTEGER NOT NULL DEFAULT 0,
        min_discount INTEGER NOT NULL DEFAULT 60,
        initialized_free INTEGER NOT NULL DEFAULT 0,
        initialized_deals INTEGER NOT NULL DEFAULT 0,
        updated_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS game_deal_seen (
        guild_id BIGINT NOT NULL, source TEXT NOT NULL, offer_id TEXT NOT NULL,
        seen_at TEXT NOT NULL,
        PRIMARY KEY (guild_id, source, offer_id)
    )""",
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
    """CREATE TABLE IF NOT EXISTS service_health (
        service TEXT PRIMARY KEY, status TEXT NOT NULL,
        message TEXT, checked_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS twitch_subscriptions (
        id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER NOT NULL,
        twitch_user_id TEXT NOT NULL, streamer_login TEXT NOT NULL,
        streamer_name TEXT NOT NULL, discord_channel_id INTEGER NOT NULL,
        mention_role_id INTEGER, profile_image_url TEXT, last_stream_id TEXT,
        is_live INTEGER NOT NULL DEFAULT 0, enabled INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL, UNIQUE(guild_id, twitch_user_id)
    )""",
    """CREATE TABLE IF NOT EXISTS kick_subscriptions (
        id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER NOT NULL,
        kick_user_id TEXT NOT NULL, streamer_slug TEXT NOT NULL,
        discord_channel_id INTEGER NOT NULL, mention_role_id INTEGER,
        is_live INTEGER NOT NULL DEFAULT 0, enabled INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL, UNIQUE(guild_id, kick_user_id)
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
        ignored_channel_ids TEXT NOT NULL DEFAULT '',
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
    """CREATE TABLE IF NOT EXISTS pc_advice_settings (
        guild_id INTEGER PRIMARY KEY, panel_channel_id INTEGER NOT NULL,
        category_id INTEGER NOT NULL, advisor_role_id INTEGER NOT NULL,
        log_channel_id INTEGER, mode TEXT NOT NULL DEFAULT 'private',
        forum_channel_id INTEGER, enabled INTEGER NOT NULL DEFAULT 1,
        reminders_enabled INTEGER NOT NULL DEFAULT 0,
        reminder_days INTEGER NOT NULL DEFAULT 3,
        updated_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS pc_advice_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER NOT NULL,
        channel_id INTEGER UNIQUE NOT NULL, user_id INTEGER NOT NULL,
        request_type TEXT NOT NULL, answers TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'open', claimed_by INTEGER,
        created_at TEXT NOT NULL, resolved_at TEXT, closed_at TEXT,
        last_reminded_message_id INTEGER
    )""",
    """CREATE TABLE IF NOT EXISTS abi_rank_settings (
        guild_id INTEGER PRIMARY KEY, review_channel_id INTEGER NOT NULL,
        reviewer_role_id INTEGER NOT NULL, rookie_role_id INTEGER,
        vanguard_role_id INTEGER, elite_role_id INTEGER, expert_role_id INTEGER,
        master_role_id INTEGER, ace_role_id INTEGER, hero_role_id INTEGER,
        legend_role_id INTEGER,
        enabled INTEGER NOT NULL DEFAULT 1, updated_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS abi_rank_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL, game_name TEXT NOT NULL, game_uid TEXT NOT NULL,
        rank_key TEXT NOT NULL, division TEXT, screenshot_url TEXT NOT NULL,
        review_message_id INTEGER, status TEXT NOT NULL DEFAULT 'pending',
        reviewer_id INTEGER, review_reason TEXT, created_at TEXT NOT NULL,
        reviewed_at TEXT
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
    """CREATE TABLE IF NOT EXISTS pc_build_challenges (
        id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER NOT NULL,
        channel_id INTEGER NOT NULL, message_id INTEGER, host_id INTEGER NOT NULL,
        budget INTEGER NOT NULL, purpose TEXT NOT NULL, end_at TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'active', created_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS pc_build_entries (
        id INTEGER PRIMARY KEY AUTOINCREMENT, challenge_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL, cpu TEXT NOT NULL, gpu TEXT NOT NULL,
        other_parts TEXT NOT NULL, total_price INTEGER NOT NULL,
        reasoning TEXT NOT NULL, created_at TEXT NOT NULL,
        UNIQUE(challenge_id, user_id)
    )""",
    """CREATE TABLE IF NOT EXISTS pc_build_votes (
        challenge_id INTEGER NOT NULL, entry_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL, created_at TEXT NOT NULL,
        PRIMARY KEY (challenge_id, user_id)
    )""",
    """CREATE TABLE IF NOT EXISTS moderation_warnings (id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER NOT NULL, user_id INTEGER NOT NULL, moderator_id INTEGER NOT NULL, reason TEXT NOT NULL, created_at TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS moderation_actions (id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER NOT NULL, user_id INTEGER NOT NULL, moderator_id INTEGER NOT NULL, action TEXT NOT NULL, reason TEXT NOT NULL, duration_minutes INTEGER, created_at TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS moderation_notes (id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER NOT NULL, user_id INTEGER NOT NULL, moderator_id INTEGER NOT NULL, note TEXT NOT NULL, created_at TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS moderation_settings (guild_id INTEGER PRIMARY KEY, auto_punishments INTEGER NOT NULL DEFAULT 0, updated_at TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS sheep_game_settings (
        guild_id INTEGER PRIMARY KEY, channel_id INTEGER,
        enabled INTEGER NOT NULL DEFAULT 0,
        current_count INTEGER NOT NULL DEFAULT 0,
        record_count INTEGER NOT NULL DEFAULT 0,
        last_user_id INTEGER, total_valid_counts INTEGER NOT NULL DEFAULT 0,
        updated_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS sheep_game_players (
        guild_id INTEGER NOT NULL, user_id INTEGER NOT NULL,
        valid_counts INTEGER NOT NULL DEFAULT 0,
        chains_broken INTEGER NOT NULL DEFAULT 0,
        updated_at TEXT NOT NULL,
        PRIMARY KEY (guild_id, user_id)
    )""",
    """CREATE TABLE IF NOT EXISTS game_deal_settings (
        guild_id INTEGER PRIMARY KEY, channel_id INTEGER, mention_role_id INTEGER,
        enabled_free INTEGER NOT NULL DEFAULT 1,
        enabled_deals INTEGER NOT NULL DEFAULT 0,
        min_discount INTEGER NOT NULL DEFAULT 60,
        initialized_free INTEGER NOT NULL DEFAULT 0,
        initialized_deals INTEGER NOT NULL DEFAULT 0,
        updated_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS game_deal_seen (
        guild_id INTEGER NOT NULL, source TEXT NOT NULL, offer_id TEXT NOT NULL,
        seen_at TEXT NOT NULL,
        PRIMARY KEY (guild_id, source, offer_id)
    )""",
)


POSTGRES_MIGRATIONS = (
    "ALTER TABLE welcome_settings ADD COLUMN IF NOT EXISTS embed_title TEXT NOT NULL DEFAULT 'Vítej!'",
    "ALTER TABLE welcome_settings ADD COLUMN IF NOT EXISTS embed_color TEXT NOT NULL DEFAULT '#5865F2'",
    "ALTER TABLE welcome_settings ADD COLUMN IF NOT EXISTS dm_enabled INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS custom_message TEXT NOT NULL DEFAULT '📺 Nové video: {title}\n{url}'",
    "ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS check_interval INTEGER NOT NULL DEFAULT 300",
    "ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS live_enabled INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS live_notify_upcoming INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS live_custom_message TEXT NOT NULL DEFAULT '🔴 {channel} právě vysílá: {title}\n{url}'",
    "ALTER TABLE pc_advice_settings ADD COLUMN IF NOT EXISTS mode TEXT NOT NULL DEFAULT 'private'",
    "ALTER TABLE pc_advice_settings ADD COLUMN IF NOT EXISTS forum_channel_id BIGINT",
    "ALTER TABLE pc_advice_settings ADD COLUMN IF NOT EXISTS reminders_enabled INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE pc_advice_settings ADD COLUMN IF NOT EXISTS reminder_days INTEGER NOT NULL DEFAULT 3",
    "ALTER TABLE pc_advice_requests ADD COLUMN IF NOT EXISTS last_reminded_message_id BIGINT",
    "ALTER TABLE abi_rank_settings ADD COLUMN IF NOT EXISTS hero_role_id BIGINT",
    "ALTER TABLE antispam_settings ADD COLUMN IF NOT EXISTS ignored_channel_ids TEXT NOT NULL DEFAULT ''",
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
        "live_enabled": "ALTER TABLE subscriptions ADD COLUMN live_enabled INTEGER NOT NULL DEFAULT 0",
        "live_notify_upcoming": "ALTER TABLE subscriptions ADD COLUMN live_notify_upcoming INTEGER NOT NULL DEFAULT 0",
        "live_custom_message": "ALTER TABLE subscriptions ADD COLUMN live_custom_message TEXT NOT NULL DEFAULT '🔴 {channel} právě vysílá: {title}\n{url}'",
    },
    "pc_advice_settings": {
        "mode": "ALTER TABLE pc_advice_settings ADD COLUMN mode TEXT NOT NULL DEFAULT 'private'",
        "forum_channel_id": "ALTER TABLE pc_advice_settings ADD COLUMN forum_channel_id INTEGER",
        "reminders_enabled": "ALTER TABLE pc_advice_settings ADD COLUMN reminders_enabled INTEGER NOT NULL DEFAULT 0",
        "reminder_days": "ALTER TABLE pc_advice_settings ADD COLUMN reminder_days INTEGER NOT NULL DEFAULT 3",
    },
    "pc_advice_requests": {
        "last_reminded_message_id": "ALTER TABLE pc_advice_requests ADD COLUMN last_reminded_message_id INTEGER",
    },
    "abi_rank_settings": {
        "hero_role_id": "ALTER TABLE abi_rank_settings ADD COLUMN hero_role_id INTEGER",
    },
    "antispam_settings": {
        "ignored_channel_ids": "ALTER TABLE antispam_settings ADD COLUMN ignored_channel_ids TEXT NOT NULL DEFAULT ''",
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
