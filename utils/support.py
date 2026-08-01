"""Konfigurace bezpečného externího odkazu pro podporu projektu."""

import os
from urllib.parse import urlparse


def get_support_url() -> str | None:
    """Vrátí pouze veřejnou HTTP(S) adresu, jinak podporu vypne."""
    value = os.getenv("SUPPORT_URL", "").strip()
    if not value:
        return None
    parsed = urlparse(value)
    if (
        len(value) > 512
        or parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
    ):
        return None
    return value
