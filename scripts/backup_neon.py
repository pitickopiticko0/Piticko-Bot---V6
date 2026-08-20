"""Vytvoří lokální PostgreSQL zálohu databáze nakonfigurované v .env."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, unquote, urlparse
from urllib.request import Request, urlopen

from dotenv import dotenv_values


PROJECT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_BACKUP_DIR = PROJECT_DIR / "backups" / "database"
ALERT_MESSAGE = (
    "🚨 **Piticko Bot:** automatická záloha PostgreSQL databáze selhala.\n"
    "Zkontroluj na VPS: `sudo journalctl -u piticko-backup.service -n 100 --no-pager`"
)


def _send_discord_alert(webhook_url: str | None, message: str) -> bool:
    if not webhook_url:
        return False
    parsed = urlparse(webhook_url)
    allowed_hosts = {"discord.com", "discordapp.com", "canary.discord.com", "ptb.discord.com"}
    if parsed.scheme != "https" or parsed.hostname not in allowed_hosts:
        print("VAROVÁNÍ: BACKUP_ALERT_WEBHOOK_URL není platný Discord webhook.", file=sys.stderr)
        return False
    if not parsed.path.startswith("/api/webhooks/"):
        print("VAROVÁNÍ: BACKUP_ALERT_WEBHOOK_URL není platný Discord webhook.", file=sys.stderr)
        return False

    payload = json.dumps({"content": message[:2000]}).encode("utf-8")
    request = Request(
        webhook_url,
        data=payload,
        headers={"Content-Type": "application/json", "User-Agent": "PitickoBot-Backup/1.0"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=10) as response:
            return 200 <= response.status < 300
    except (HTTPError, URLError, TimeoutError) as error:
        print(f"VAROVÁNÍ: Discord upozornění se nepodařilo odeslat: {error}", file=sys.stderr)
        return False


def _postgres_environment(database_url: str) -> dict[str, str]:
    """Převede PostgreSQL URL na libpq proměnné bez hesla v argumentech procesu."""
    parsed = urlparse(database_url)
    if parsed.scheme not in {"postgres", "postgresql"}:
        raise RuntimeError("DATABASE_URL není platná PostgreSQL URL.")

    database_name = unquote(parsed.path.lstrip("/"))
    if not database_name:
        raise RuntimeError("DATABASE_URL neobsahuje název databáze.")

    # URL bez hostitele (např. postgresql:///piticko_bot) používá lokální
    # Unix socket a peer autentizaci. Vzdálené URL mohou dodat hostitele,
    # port, uživatele i heslo; chybějící údaje případně vyřeší libpq.
    values = {"PGDATABASE": database_name}
    if parsed.hostname:
        values["PGHOST"] = parsed.hostname
        values["PGPORT"] = str(parsed.port or 5432)
    if parsed.username:
        values["PGUSER"] = unquote(parsed.username)
    if parsed.password is not None:
        values["PGPASSWORD"] = unquote(parsed.password)
    query = parse_qs(parsed.query)
    query_environment = {
        "sslmode": "PGSSLMODE",
        "channel_binding": "PGCHANNELBINDING",
        "options": "PGOPTIONS",
        "application_name": "PGAPPNAME",
    }
    for query_name, environment_name in query_environment.items():
        if query.get(query_name):
            values[environment_name] = query[query_name][-1]
    return values


def _positive_days(raw_value: str | None) -> int:
    try:
        days = int(raw_value or "14")
    except ValueError as error:
        raise RuntimeError("DATABASE_BACKUP_RETENTION_DAYS musí být celé číslo.") from error
    if days < 1:
        raise RuntimeError("DATABASE_BACKUP_RETENTION_DAYS musí být alespoň 1.")
    return days


def _remove_expired_backups(directory: Path, retention_days: int) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    removed = 0
    for backup in directory.glob("piticko-db-*.dump"):
        modified = datetime.fromtimestamp(backup.stat().st_mtime, timezone.utc)
        if modified < cutoff:
            backup.unlink()
            removed += 1
    return removed


def _upload_offsite_backup(backup: Path, remote: str, retention_days: int) -> None:
    """Nahraje zálohu přes rclone a odstraní jen staré zálohy tohoto projektu."""
    remote = remote.strip().rstrip("/")
    if not remote or remote.startswith("-") or ":" not in remote:
        raise RuntimeError("BACKUP_RCLONE_REMOTE není platný rclone cíl.")

    rclone = shutil.which("rclone")
    if not rclone:
        raise RuntimeError("rclone není nainstalovaný nebo není v PATH.")

    subprocess.run(
        [rclone, "copyto", str(backup), f"{remote}/{backup.name}"],
        cwd=PROJECT_DIR,
        check=True,
        timeout=1800,
    )
    subprocess.run(
        [
            rclone,
            "delete",
            remote,
            "--include",
            "piticko-db-*.dump",
            "--min-age",
            f"{retention_days}d",
        ],
        cwd=PROJECT_DIR,
        check=True,
        timeout=1800,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Záloha PostgreSQL databáze")
    parser.add_argument(
        "--test-alert",
        action="store_true",
        help="odešle pouze testovací Discord upozornění a nevytvoří zálohu",
    )
    args = parser.parse_args()

    config = dotenv_values(PROJECT_DIR / ".env")
    alert_url = config.get("BACKUP_ALERT_WEBHOOK_URL") or os.getenv(
        "BACKUP_ALERT_WEBHOOK_URL"
    )
    if args.test_alert:
        if not alert_url:
            print("CHYBA: BACKUP_ALERT_WEBHOOK_URL není nastavený.", file=sys.stderr)
            return 1
        try:
            sent = _send_discord_alert(
                str(alert_url),
                "✅ **Piticko Bot:** test upozornění zálohovací služby proběhl úspěšně.",
            )
        except RuntimeError as error:
            print(f"CHYBA: {error}", file=sys.stderr)
            return 1
        print("Testovací upozornění bylo odesláno." if sent else "Test selhal.")
        return 0 if sent else 1

    database_url = config.get("DATABASE_URL") or os.getenv("DATABASE_URL")
    if not database_url:
        print("CHYBA: DATABASE_URL není nastavená.", file=sys.stderr)
        _send_discord_alert(str(alert_url) if alert_url else None, ALERT_MESSAGE)
        return 1

    pg_dump = shutil.which("pg_dump")
    if not pg_dump:
        print("CHYBA: pg_dump není nainstalovaný.", file=sys.stderr)
        _send_discord_alert(str(alert_url) if alert_url else None, ALERT_MESSAGE)
        return 1

    retention_days = _positive_days(
        config.get("DATABASE_BACKUP_RETENTION_DAYS")
        or os.getenv("DATABASE_BACKUP_RETENTION_DAYS")
    )
    configured_dir = config.get("DATABASE_BACKUP_DIR") or os.getenv("DATABASE_BACKUP_DIR")
    backup_dir = Path(configured_dir).expanduser() if configured_dir else DEFAULT_BACKUP_DIR
    rclone_remote = config.get("BACKUP_RCLONE_REMOTE") or os.getenv(
        "BACKUP_RCLONE_REMOTE"
    )
    backup_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    backup_dir.chmod(0o700)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = backup_dir / f"piticko-db-{timestamp}.dump"
    temporary = output.with_suffix(".dump.tmp")

    try:
        environment = os.environ.copy()
        environment.update(_postgres_environment(str(database_url)))
        subprocess.run(
            [
                pg_dump,
                "--format=custom",
                "--compress=6",
                "--no-owner",
                "--no-privileges",
                "--file",
                str(temporary),
            ],
            cwd=PROJECT_DIR,
            env=environment,
            check=True,
            timeout=1800,
        )
        if not temporary.exists() or temporary.stat().st_size == 0:
            raise RuntimeError("pg_dump vytvořil prázdný soubor.")
        temporary.chmod(0o600)
        temporary.replace(output)
        removed = _remove_expired_backups(backup_dir, retention_days)
        if rclone_remote:
            _upload_offsite_backup(output, str(rclone_remote), retention_days)
    except (OSError, subprocess.SubprocessError, RuntimeError) as error:
        temporary.unlink(missing_ok=True)
        print(f"CHYBA: záloha databáze selhala: {error}", file=sys.stderr)
        try:
            _send_discord_alert(str(alert_url) if alert_url else None, ALERT_MESSAGE)
        except RuntimeError as alert_error:
            print(f"VAROVÁNÍ: {alert_error}", file=sys.stderr)
        return 1

    size_mb = output.stat().st_size / 1024 / 1024
    offsite = f", nahrána na {rclone_remote}" if rclone_remote else ""
    print(
        f"Záloha vytvořena: {output.name} ({size_mb:.1f} MB), "
        f"odstraněno starých: {removed}{offsite}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
