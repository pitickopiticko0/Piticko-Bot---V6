import sqlite3
import unittest

from utils.db import pc_catalog


class _ConnectionContext:
    def __init__(self, connection):
        self.connection = connection

    def __enter__(self):
        return self.connection

    def __exit__(self, exc_type, exc, tb):
        return False


class MemoryDatabase:
    using_postgres = False

    def __init__(self):
        self.connection = sqlite3.connect(":memory:")
        self.connection.row_factory = sqlite3.Row
        self.connection.execute(
            """CREATE TABLE pc_catalog_settings (
                guild_id INTEGER PRIMARY KEY,
                forum_channel_id INTEGER,
                mention_role_id INTEGER,
                buildz_forum_channel_id INTEGER,
                buildz_mention_role_id INTEGER,
                enabled INTEGER NOT NULL DEFAULT 0,
                enabled_makejpc INTEGER NOT NULL DEFAULT 0,
                enabled_sestavsipocitac INTEGER NOT NULL DEFAULT 0,
                enabled_buildz INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL
            )"""
        )

    def connect(self):
        return _ConnectionContext(self.connection)

    @staticmethod
    def now():
        return "2026-09-17T00:00:00+00:00"


class PcCatalogSettingsTests(unittest.TestCase):
    def setUp(self):
        self.db = MemoryDatabase()

    def tearDown(self):
        self.db.connection.close()

    def test_sources_keep_their_own_forums_and_roles(self):
        pc_catalog.save_settings(
            self.db,
            1,
            101,
            201,
            102,
            202,
            True,
            False,
            True,
            True,
        )

        row = pc_catalog.get_settings(self.db, 1)
        self.assertEqual(row["forum_channel_id"], 101)
        self.assertEqual(row["mention_role_id"], 201)
        self.assertEqual(row["buildz_forum_channel_id"], 102)
        self.assertEqual(row["buildz_mention_role_id"], 202)

    def test_enabled_settings_needs_a_forum_for_an_enabled_source(self):
        pc_catalog.save_settings(
            self.db,
            1,
            None,
            None,
            None,
            None,
            True,
            False,
            True,
            True,
        )
        self.assertEqual(pc_catalog.get_enabled_settings(self.db), [])

        pc_catalog.save_settings(
            self.db,
            1,
            None,
            None,
            102,
            None,
            True,
            False,
            True,
            True,
        )
        self.assertEqual(len(pc_catalog.get_enabled_settings(self.db)), 1)


if __name__ == "__main__":
    unittest.main()
