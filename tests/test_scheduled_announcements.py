"""Základní test úložiště plánovaných oznámení."""

from __future__ import annotations

import sqlite3
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from utils.db import migrations, scheduled_announcements


class TestDatabase:
    """Malý SQLite adapter: testuje modul bez závislosti na .env a dotenv."""

    using_postgres = False

    def __init__(self, path: Path) -> None:
        self.path = path
        migrations.initialize(self)

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
        finally:
            connection.close()

    @staticmethod
    def now() -> str:
        return datetime.now(timezone.utc).isoformat()


def main() -> None:
    with tempfile.TemporaryDirectory() as directory:
        database = TestDatabase(Path(directory) / "announcements.db")
        announcement_id = scheduled_announcements.create(
            database,
            123, 456, 789, "Test", "Naplánovaná zpráva", "#5865F2",
            "2030-01-01T10:00:00+00:00",
        )
        assert announcement_id > 0
        assert len(scheduled_announcements.list_for_guild(database, 123)) == 1
        assert scheduled_announcements.list_due(database, "2029-01-01T00:00:00+00:00") == []
        assert len(scheduled_announcements.list_due(database, "2031-01-01T00:00:00+00:00")) == 1

        assert scheduled_announcements.update(
            database,
            announcement_id, 123, 457, "Upraveno", "Nový text", "#112233",
            "2030-01-02T10:00:00+00:00",
        )
        announcement = scheduled_announcements.get_for_guild(database, announcement_id, 123)
        assert announcement["channel_id"] == 457
        assert announcement["title"] == "Upraveno"

        assert scheduled_announcements.cancel(database, announcement_id, 123)
        assert scheduled_announcements.list_due(database, "2031-01-01T00:00:00+00:00") == []

        repeating_id = scheduled_announcements.create(
            database,
            123, 456, 789, "Denní test", "Text", "#5865F2",
            "2030-01-01T10:00:00+00:00", "daily", "Europe/Prague",
        )
        scheduled_announcements.reschedule(
            database, repeating_id, 987, "2030-01-02T10:00:00+00:00"
        )
        repeating = scheduled_announcements.get_for_guild(database, repeating_id, 123)
        assert repeating["status"] == "scheduled"
        assert repeating["repeat_kind"] == "daily"
        assert repeating["timezone_name"] == "Europe/Prague"
        assert repeating["scheduled_at"] == "2030-01-02T10:00:00+00:00"

    print("OK: scheduled announcements")


if __name__ == "__main__":
    main()
