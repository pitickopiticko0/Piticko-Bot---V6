import asyncio
import sqlite3
import sys
import types
import unittest

try:
    import aiohttp  # noqa: F401
except ImportError:
    # Parserové testy nahrazují síťovou metodu, aiohttp proto nepotřebují.
    sys.modules["aiohttp"] = types.ModuleType("aiohttp")

from services.game_deals import GameDealsAPI
from utils.db import game_deals


class MemoryDatabase:
    using_postgres = False

    def __init__(self):
        self.connection = sqlite3.connect(":memory:")
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript(
            """
            CREATE TABLE game_deal_settings (
                guild_id INTEGER PRIMARY KEY, channel_id INTEGER,
                mention_role_id INTEGER, enabled_free INTEGER DEFAULT 1,
                enabled_deals INTEGER DEFAULT 0, min_discount INTEGER DEFAULT 60,
                initialized_free INTEGER DEFAULT 0,
                initialized_deals INTEGER DEFAULT 0, updated_at TEXT NOT NULL
            );
            CREATE TABLE game_deal_seen (
                guild_id INTEGER, source TEXT, offer_id TEXT, seen_at TEXT,
                PRIMARY KEY (guild_id, source, offer_id)
            );
            """
        )

    def connect(self):
        return _ConnectionContext(self.connection)

    @staticmethod
    def now():
        return "2026-08-19T00:00:00+00:00"


class _ConnectionContext:
    def __init__(self, connection):
        self.connection = connection

    def __enter__(self):
        return self.connection

    def __exit__(self, exc_type, exc, tb):
        return False


class GameDealsDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.db = MemoryDatabase()

    def tearDown(self):
        self.db.connection.close()

    def test_settings_seen_and_initialization(self):
        game_deals.save_settings(self.db, 1, 123, 456, True, True, 70)
        row = game_deals.get_settings(self.db, 1)
        self.assertEqual(row["min_discount"], 70)
        self.assertFalse(game_deals.is_seen(self.db, 1, "source", "offer"))
        game_deals.mark_seen(self.db, 1, "source", "offer")
        game_deals.mark_seen(self.db, 1, "source", "offer")
        self.assertTrue(game_deals.is_seen(self.db, 1, "source", "offer"))
        self.assertEqual(game_deals.count_seen(self.db, 1), 1)
        game_deals.set_initialized(self.db, 1, "free")
        self.assertTrue(game_deals.is_initialized(self.db, 1, "free"))

    def test_discount_is_clamped(self):
        game_deals.save_settings(self.db, 1, 123, None, False, True, 500)
        self.assertEqual(game_deals.get_settings(self.db, 1)["min_discount"], 95)


class GameDealsParserTests(unittest.TestCase):
    def test_parsers_ignore_invalid_items(self):
        api = GameDealsAPI()
        responses = iter(
            [
                [
                    {
                        "id": 10,
                        "title": "Free Game",
                        "status": "Active",
                        "platforms": "PC, Steam",
                        "open_giveaway_url": "https://example.test/free",
                        "worth": "$10",
                    },
                    {"id": 11, "title": "Console", "platforms": "PS5"},
                ],
                [{"storeID": "1", "storeName": "Steam", "isActive": 1}],
                [
                    {
                        "dealID": "abc=",
                        "title": "Sale Game",
                        "savings": "75.4",
                        "salePrice": "5",
                        "normalPrice": "20",
                        "storeID": "1",
                    },
                    {"dealID": "bad", "title": "Bad", "savings": "x"},
                ],
            ]
        )

        async def fake_json(*args, **kwargs):
            return next(responses)

        api._json = fake_json

        async def run():
            free = await api.fetch_free_games()
            deals = await api.fetch_discounted_games()
            return free, deals

        free, deals = asyncio.run(run())
        self.assertEqual([offer.title for offer in free], ["Free Game"])
        self.assertEqual([offer.title for offer in deals], ["Sale Game"])
        self.assertEqual(deals[0].discount, 75)
        self.assertIn("abc%3D", deals[0].url)


if __name__ == "__main__":
    unittest.main()
