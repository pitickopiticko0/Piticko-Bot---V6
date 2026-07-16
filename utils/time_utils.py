from datetime import datetime


def format_discord_time(iso_time: str | None) -> str | None:
    """
    Převod YouTube času typu:
    2026-07-02T15:56:40Z

    na Discord timestamp:
    <t:1783007800:F>

    Discord ho potom každému uživateli zobrazí podle jeho časové zóny.
    """
    if not iso_time:
        return None

    try:
        dt = datetime.fromisoformat(iso_time.replace("Z", "+00:00"))
        timestamp = int(dt.timestamp())
        return f"<t:{timestamp}:F>"
    except ValueError:
        return iso_time
