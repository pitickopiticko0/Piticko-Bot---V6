"""Základní test ukládání mapování reakcí na role."""

import gc
import os
import sys
import tempfile
from pathlib import Path

os.environ.pop("DATABASE_URL", None)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils.database import Database
from utils.db.reaction_roles import normalize_entries


def run() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        database = Database(Path(temp_dir) / "reaction-roles.db")
        database.add_guild(1, "Test server")
        entries = normalize_entries([
            {"emoji": "🎮", "role_id": "101"},
            {"emoji": "🔔", "role_id": "102"},
        ])
        database.save_reaction_role_settings(
            1,
            55,
            "Vyber si role",
            "Klikni na emoji.",
            entries,
            enabled=True,
        )
        saved = database.get_reaction_role_settings(1)
        assert saved["enabled"] is True
        assert saved["message_id"] == ""
        assert saved["entries"] == [
            {"emoji": "🎮", "role_id": "101"},
            {"emoji": "🔔", "role_id": "102"},
        ]
        database.set_reaction_role_message_id(1, 999)
        assert database.get_reaction_role_mapping(1, 999, "🎮") == 101
        assert database.get_reaction_role_mapping(1, 999, "❌") is None
        try:
            normalize_entries([
                {"emoji": "🎮", "role_id": "101"},
                {"emoji": "🎮", "role_id": "102"},
            ])
        except ValueError:
            pass
        else:
            raise AssertionError("Duplicitní emoji musí být odmítnuto.")
        del database
        gc.collect()

    print("OK: reaction roles")


if __name__ == "__main__":
    run()
