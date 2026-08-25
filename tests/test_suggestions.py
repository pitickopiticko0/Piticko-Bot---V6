"""Základní test databázové vrstvy komunitních návrhů."""

from __future__ import annotations

import tempfile
import gc
from pathlib import Path

from utils.database import Database


def main() -> None:
    with tempfile.TemporaryDirectory() as directory:
        database = Database(Path(directory) / "suggestions.db")
        database.set_suggestion_settings(123, 456, True)
        settings = database.get_suggestion_settings(123)
        assert settings["enabled"] is True
        assert settings["channel_id"] == "456"

        suggestion_id = database.create_suggestion(
            123, 456, 999, "Přidat kanál", "Přidejme kanál pro společné hraní."
        )
        assert database.vote_suggestion(suggestion_id, 10, 1) == (1, 0)
        assert database.vote_suggestion(suggestion_id, 11, -1) == (1, 1)
        # Druhý hlas stejného člověka má změnit jeho volbu, ne přidat další hlas.
        assert database.vote_suggestion(suggestion_id, 10, -1) == (0, 2)

        database.set_suggestion_status(suggestion_id, "accepted", 50, "Přidáme ho.")
        suggestion = database.get_suggestion(suggestion_id)
        assert suggestion["status"] == "accepted"
        assert suggestion["moderator_response"] == "Přidáme ho."
        assert len(database.get_recent_suggestions(123)) == 1
        del database
        gc.collect()

    print("OK: suggestions")


if __name__ == "__main__":
    main()
