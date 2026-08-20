import sys
import types
import unittest

try:
    import dotenv  # noqa: F401
except ModuleNotFoundError:
    dotenv_stub = types.ModuleType("dotenv")
    dotenv_stub.dotenv_values = lambda *args, **kwargs: {}
    sys.modules["dotenv"] = dotenv_stub

from scripts.backup_neon import _postgres_environment


class PostgreSQLEnvironmentTests(unittest.TestCase):
    def test_local_socket_url(self):
        self.assertEqual(
            _postgres_environment("postgresql:///piticko_bot"),
            {"PGDATABASE": "piticko_bot"},
        )

    def test_remote_url(self):
        self.assertEqual(
            _postgres_environment(
                "postgresql://bot:secret@db.example.test:5433/piticko?sslmode=require"
            ),
            {
                "PGHOST": "db.example.test",
                "PGPORT": "5433",
                "PGUSER": "bot",
                "PGPASSWORD": "secret",
                "PGDATABASE": "piticko",
                "PGSSLMODE": "require",
            },
        )

    def test_database_name_is_required(self):
        with self.assertRaisesRegex(RuntimeError, "název databáze"):
            _postgres_environment("postgresql://db.example.test")


if __name__ == "__main__":
    unittest.main()
