"""Databázové operace pro minihru Výzva PC stavitelů."""

from typing import Any


def create_challenge(database: Any, guild_id: int, channel_id: int, host_id: int,
                     budget: int, purpose: str, end_at: str) -> int:
    with database.connect() as conn:
        values = (guild_id, channel_id, host_id, budget, purpose, end_at, database.now())
        sql = """INSERT INTO pc_build_challenges
            (guild_id, channel_id, host_id, budget, purpose, end_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)"""
        if database.using_postgres:
            row = conn.execute(sql + " RETURNING id", values).fetchone()
            challenge_id = int(row["id"])
        else:
            challenge_id = int(conn.execute(sql, values).lastrowid)
        conn.commit()
        return challenge_id


def get_challenge(database: Any, challenge_id: int):
    with database.connect() as conn:
        return conn.execute("SELECT * FROM pc_build_challenges WHERE id = ?", (challenge_id,)).fetchone()


def get_open_challenges(database: Any):
    with database.connect() as conn:
        return conn.execute(
            "SELECT * FROM pc_build_challenges WHERE status IN ('active', 'voting')"
        ).fetchall()


def get_recent_challenges(database: Any, guild_id: int, limit: int = 20):
    safe_limit = max(1, min(int(limit), 100))
    with database.connect() as conn:
        return conn.execute(
            """SELECT c.*,
                (SELECT COUNT(*) FROM pc_build_entries e
                 WHERE e.challenge_id = c.id) AS entry_count,
                (SELECT COUNT(*) FROM pc_build_votes v
                 WHERE v.challenge_id = c.id) AS vote_count
            FROM pc_build_challenges c
            WHERE c.guild_id = ?
            ORDER BY c.id DESC
            LIMIT ?""",
            (guild_id, safe_limit),
        ).fetchall()


def set_message(database: Any, challenge_id: int, message_id: int) -> None:
    with database.connect() as conn:
        conn.execute("UPDATE pc_build_challenges SET message_id = ? WHERE id = ?", (message_id, challenge_id))
        conn.commit()


def set_status(database: Any, challenge_id: int, status: str) -> None:
    with database.connect() as conn:
        conn.execute("UPDATE pc_build_challenges SET status = ? WHERE id = ?", (status, challenge_id))
        conn.commit()


def add_entry(database: Any, challenge_id: int, user_id: int, cpu: str, gpu: str,
              other_parts: str, total_price: int, reasoning: str) -> bool:
    with database.connect() as conn:
        cursor = conn.execute("""INSERT INTO pc_build_entries
            (challenge_id, user_id, cpu, gpu, other_parts, total_price, reasoning, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (challenge_id, user_id) DO NOTHING""",
            (challenge_id, user_id, cpu, gpu, other_parts, total_price, reasoning, database.now()))
        conn.commit()
        return cursor.rowcount > 0


def get_entries(database: Any, challenge_id: int):
    with database.connect() as conn:
        return conn.execute("SELECT * FROM pc_build_entries WHERE challenge_id = ? ORDER BY id", (challenge_id,)).fetchall()


def vote(database: Any, challenge_id: int, entry_id: int, user_id: int) -> None:
    with database.connect() as conn:
        conn.execute("""INSERT INTO pc_build_votes (challenge_id, entry_id, user_id, created_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT (challenge_id, user_id) DO UPDATE SET
            entry_id = EXCLUDED.entry_id, created_at = EXCLUDED.created_at""",
            (challenge_id, entry_id, user_id, database.now()))
        conn.commit()


def results(database: Any, challenge_id: int):
    with database.connect() as conn:
        return conn.execute("""SELECT e.*, COUNT(v.user_id) AS votes
            FROM pc_build_entries e LEFT JOIN pc_build_votes v ON v.entry_id = e.id
            WHERE e.challenge_id = ? GROUP BY e.id
            ORDER BY votes DESC, e.id ASC""", (challenge_id,)).fetchall()
