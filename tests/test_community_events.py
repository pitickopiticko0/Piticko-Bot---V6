"""Základní test úložiště komunitních akcí."""

from __future__ import annotations

import sqlite3
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from utils.db import events, migrations


class TestDatabase:
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
        database = TestDatabase(Path(directory) / "events.db")
        event_id = events.create(
            database, 123, 456, 789, "Společné hraní", "Večer hrajeme CS2.",
            "2030-01-01T18:00:00+00:00",
        )
        assert len(events.list_pending(database)) == 1
        events.set_published(database, event_id, 111)
        assert events.join(database, event_id, 1001) is True
        assert events.join(database, event_id, 1001) is False
        assert events.count_participants(database, event_id) == 1
        event = events.get(database, event_id, 123)
        assert event["status"] == "active"
        assert events.cancel(database, event_id, 123) is True
        assert events.get(database, event_id, 123)["status"] == "cancelled"

    print("OK: community events")


if __name__ == "__main__":
    main()
