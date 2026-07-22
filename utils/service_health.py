from typing import Optional

from utils.database import db


def _save(service: str, status: str, message: Optional[str]) -> None:
    try:
        with db.connect() as conn:
            excluded = "EXCLUDED" if db.using_postgres else "excluded"
            conn.execute(f"""
                INSERT INTO service_health (service, status, message, checked_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT (service) DO UPDATE SET
                    status = {excluded}.status,
                    message = {excluded}.message,
                    checked_at = {excluded}.checked_at
            """, (service, status, (message or "")[:1000], db.now()))
            conn.commit()
    except Exception:
        # Diagnostika nesmí shodit samotný watcher, zejména při výpadku DB.
        return


def mark_success(service: str, message: str = "Kontrola proběhla úspěšně.") -> None:
    _save(service, "ok", message)


def mark_error(service: str, error: object) -> None:
    _save(service, "error", str(error))


def get_all():
    with db.connect() as conn:
        return conn.execute(
            "SELECT service, status, message, checked_at FROM service_health ORDER BY service"
        ).fetchall()
