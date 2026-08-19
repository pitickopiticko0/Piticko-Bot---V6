import sqlite3
import unittest
from datetime import datetime, timezone

from utils.db import migrations
from utils.db import sheep_game


class MemoryDatabase:
    using_postgres = False

    def __init__(self) -> None:
        self.connection = sqlite3.connect(":memory:")
        self.connection.row_factory = sqlite3.Row
        for statement in migrations.SQLITE_TABLES:
            self.connection.execute(statement)
        self.connection.commit()

    def connect(self):
        return ConnectionContext(self.connection)

    @staticmethod
    def now() -> str:
        return datetime.now(timezone.utc).isoformat()


class ConnectionContext:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def __enter__(self) -> sqlite3.Connection:
        return self.connection

    def __exit__(self, exc_type, exc, traceback) -> bool:
        return False


class SheepGameDatabaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.db = MemoryDatabase()
        sheep_game.save_settings(self.db, 1, 123, True)

    def tearDown(self) -> None:
        self.db.connection.close()

    def test_valid_counts_update_chain_record_and_player(self) -> None:
        sheep_game.record_valid_count(self.db, 1, 10, 1)
        sheep_game.record_valid_count(self.db, 1, 20, 2)

        settings = sheep_game.get_settings(self.db, 1)
        self.assertEqual(settings["current_count"], 2)
        self.assertEqual(settings["record_count"], 2)
        self.assertEqual(settings["total_valid_counts"], 2)
        self.assertEqual(settings["last_user_id"], 20)
        self.assertEqual(len(sheep_game.get_leaderboard(self.db, 1)), 2)

    def test_broken_chain_keeps_record_and_counts_failure(self) -> None:
        sheep_game.record_valid_count(self.db, 1, 10, 1)
        previous = sheep_game.break_chain(self.db, 1, 20)

        settings = sheep_game.get_settings(self.db, 1)
        player = sheep_game.get_leaderboard(self.db, 1)[1]
        self.assertEqual(previous, 1)
        self.assertEqual(settings["current_count"], 0)
        self.assertEqual(settings["record_count"], 1)
        self.assertEqual(player["chains_broken"], 1)


if __name__ == "__main__":
    unittest.main()
