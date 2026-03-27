"""
Migration: backfill title_normalized for all existing songs.
Run AFTER 007_search_optimization.sql has been executed.

Usage:
    cd lyric360_backend
    source .venv/bin/activate
    python -m migrations.008_backfill_title_normalized
"""

import sys, os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import text
from database import engine
from utils.text import normalize_vn


def run():
    with engine.begin() as conn:
        rows = conn.execute(text("SELECT id, title FROM songs WHERE title_normalized IS NULL")).fetchall()
        print(f"Found {len(rows)} songs to backfill...")

        for row in rows:
            conn.execute(
                text("UPDATE songs SET title_normalized = :norm WHERE id = :id"),
                {"norm": normalize_vn(row.title), "id": str(row.id)},
            )

        print(f"Backfilled {len(rows)} songs.")


if __name__ == "__main__":
    run()