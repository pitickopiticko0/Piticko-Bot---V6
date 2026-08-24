"""Základní testy databázové ochrany kola štěstí."""

import os
import sys
import tempfile
from pathlib import Path

os.environ.pop("DATABASE_URL", None)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils.database import Database


def run() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        database = Database(Path(temp_dir) / "wheel.db")
        database.add_guild(1, "Test server")
        first, player = database.spin_lucky_wheel(1, 10, 20, "Test hráč")
        assert first is True
        assert player["points"] == 20
        second, player = database.spin_lucky_wheel(1, 10, 100, "Test hráč")
        assert second is False
        assert player["points"] == 20
        assert database.get_lucky_wheel_guild_name(1) == "Test server"
        assert database.get_lucky_wheel_leaderboard(1)[0]["display_name"] == "Test hráč"

    print("OK: lucky wheel")


if __name__ == "__main__":
    run()
