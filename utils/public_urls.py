"""Odkazy na veřejnou část webového dashboardu."""

import os
from urllib.parse import urlsplit


def get_public_dashboard_url() -> str | None:
    """Vrátí veřejnou adresu dashboardu bez koncového lomítka.

    Pro produkci nastav ``DASHBOARD_PUBLIC_URL=https://moje-domena``. Pokud
    proměnná chybí, lze adresu bezpečně odvodit z OAuth callbacku.
    """
    configured = os.getenv("DASHBOARD_PUBLIC_URL", "").strip().rstrip("/")
    if configured:
        parsed = urlsplit(configured)
        return configured if parsed.netloc and parsed.scheme in {"http", "https"} else None

    redirect_uri = os.getenv("DASHBOARD_REDIRECT_URI", "").strip()
    parsed = urlsplit(redirect_uri)
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}"
    return None


def lucky_wheel_url(guild_id: int) -> str | None:
    base_url = get_public_dashboard_url()
    if not base_url:
        return None
    return f"{base_url}/kolo/{int(guild_id)}"
