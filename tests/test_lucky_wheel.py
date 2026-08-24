"""Základní testy nastavení veřejného kola štěstí."""

import os
import sys
import tempfile
import gc
from pathlib import Path

os.environ.pop("DATABASE_URL", None)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils.database import Database
from utils.db.lucky_wheel import parse_entries_text


def run() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        database = Database(Path(temp_dir) / "wheel.db")
        database.add_guild(1, "Test server")
        initial = database.get_lucky_wheel_settings(1)
        assert len(initial["entries"]) == 6
        entries = parse_entries_text(
            "🎁 | Malá výhra | #F5B93D | 1\n🍀 | Štěstí | #45C98B | 3"
        )
        database.save_lucky_wheel_settings(1, "Testovací kolo", "Bez bodů", entries)
        saved = database.get_lucky_wheel_settings(1)
        assert saved["title"] == "Testovací kolo"
        assert saved["entries"] == entries
        assert database.get_lucky_wheel_guild_name(1) == "Test server"
        # Database používá krátkodobá sqlite spojení; na Windows je před
        # odstraněním dočasné složky explicitně uvolníme.
        del database
        gc.collect()

    print("OK: lucky wheel")


if __name__ == "__main__":
    run()
