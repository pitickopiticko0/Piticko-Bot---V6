"""Vytvoří lokální PostgreSQL zálohu databáze nakonfigurované v .env."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import shutil
import subprocess
import sys

from dotenv import dotenv_values


PROJECT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_BACKUP_DIR = PROJECT_DIR / "backups" / "database"


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


def main() -> int:
    config = dotenv_values(PROJECT_DIR / ".env")
    database_url = config.get("DATABASE_URL") or os.getenv("DATABASE_URL")
    if not database_url:
        print("CHYBA: DATABASE_URL není nastavená.", file=sys.stderr)
        return 1

    pg_dump = shutil.which("pg_dump")
    if not pg_dump:
        print("CHYBA: pg_dump není nainstalovaný.", file=sys.stderr)
        return 1

    retention_days = _positive_days(
        config.get("DATABASE_BACKUP_RETENTION_DAYS")
        or os.getenv("DATABASE_BACKUP_RETENTION_DAYS")
    )
    configured_dir = config.get("DATABASE_BACKUP_DIR") or os.getenv("DATABASE_BACKUP_DIR")
    backup_dir = Path(configured_dir).expanduser() if configured_dir else DEFAULT_BACKUP_DIR
    backup_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    backup_dir.chmod(0o700)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = backup_dir / f"piticko-db-{timestamp}.dump"
    temporary = output.with_suffix(".dump.tmp")

    environment = os.environ.copy()
    # Připojovací řetězec předáváme pg_dump přes prostředí, ne přes argumenty procesu.
    environment["PGDATABASE"] = str(database_url)

    try:
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
    except (OSError, subprocess.SubprocessError, RuntimeError) as error:
        temporary.unlink(missing_ok=True)
        print(f"CHYBA: záloha databáze selhala: {error}", file=sys.stderr)
        return 1

    size_mb = output.stat().st_size / 1024 / 1024
    print(f"Záloha vytvořena: {output.name} ({size_mb:.1f} MB), odstraněno starých: {removed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
