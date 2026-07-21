"""Vykreslení vlastního textu YouTube oznámení z dashboardu."""

from typing import Optional


DEFAULT_TEMPLATE = "📺 Nové video: {title}\n{url}"
DISCORD_MESSAGE_LIMIT = 2000


def _escape_mentions(value: str) -> str:
    """Zabrání názvu videa nebo kanálu nechtěně pingnout uživatele."""
    return value.replace("@", "@\u200b")


def render_youtube_message(
    template: Optional[str],
    *,
    title: str,
    url: str,
    channel: str,
    channel_url: str,
    thumbnail: Optional[str],
    published: Optional[str],
    role: Optional[str],
) -> str:
    source = (template or DEFAULT_TEMPLATE).strip()
    contains_role_variable = "{role}" in source
    values = {
        "title": _escape_mentions(title),
        "url": url,
        "channel": _escape_mentions(channel),
        "channel_url": channel_url,
        "thumbnail": thumbnail or "",
        "published": published or "",
        "role": role or "",
    }

    rendered = source
    for name, value in values.items():
        rendered = rendered.replace(f"{{{name}}}", value)

    # Starší uložené šablony nemají {role}; nastavený ping přesto zachováme.
    if role and not contains_role_variable:
        rendered = f"{role}\n\n{rendered}"

    rendered = rendered.strip()
    if len(rendered) > DISCORD_MESSAGE_LIMIT:
        rendered = f"{rendered[:DISCORD_MESSAGE_LIMIT - 1]}…"
    return rendered
