"""
Migration: remove duplicate songs (same title), remapping all FK references
to the kept record before deleting duplicates.

Keeper = oldest record per title (smallest created_at).

Tables remapped: queue_registrations, song_sheets, song_lyrics

Usage:
    cd lyric360_backend
    source .venv/bin/activate
    python -m "migrations.004_remove duplicate"
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import text
from database import engine

# Remap queue_registrations.song_id from duplicate → keeper
REMAP_QUEUE = """
WITH keepers AS (
    SELECT DISTINCT ON (LOWER(title)) id AS keep_id, title
    FROM songs
    ORDER BY LOWER(title), created_at ASC
),
to_remove AS (
    SELECT s.id AS remove_id, k.keep_id
    FROM songs s
    JOIN keepers k ON LOWER(s.title) = LOWER(k.title)
    WHERE s.id <> k.keep_id
)
UPDATE queue_registrations
SET song_id = to_remove.keep_id
FROM to_remove
WHERE queue_registrations.song_id = to_remove.remove_id;
"""

# Remap song_sheets.song_id from duplicate → keeper
REMAP_SHEETS = """
WITH keepers AS (
    SELECT DISTINCT ON (LOWER(title)) id AS keep_id, title
    FROM songs
    ORDER BY LOWER(title), created_at ASC
),
to_remove AS (
    SELECT s.id AS remove_id, k.keep_id
    FROM songs s
    JOIN keepers k ON LOWER(s.title) = LOWER(k.title)
    WHERE s.id <> k.keep_id
)
UPDATE song_sheets
SET song_id = to_remove.keep_id
FROM to_remove
WHERE song_sheets.song_id = to_remove.remove_id;
"""

# Remap song_lyrics.song_id from duplicate → keeper
REMAP_LYRICS = """
WITH keepers AS (
    SELECT DISTINCT ON (LOWER(title)) id AS keep_id, title
    FROM songs
    ORDER BY LOWER(title), created_at ASC
),
to_remove AS (
    SELECT s.id AS remove_id, k.keep_id
    FROM songs s
    JOIN keepers k ON LOWER(s.title) = LOWER(k.title)
    WHERE s.id <> k.keep_id
)
UPDATE song_lyrics
SET song_id = to_remove.keep_id
FROM to_remove
WHERE song_lyrics.song_id = to_remove.remove_id;
"""

# Delete duplicate songs (keepers are preserved)
DELETE_DUPLICATES = """
WITH keepers AS (
    SELECT DISTINCT ON (LOWER(title)) id AS keep_id
    FROM songs
    ORDER BY LOWER(title), created_at ASC
)
DELETE FROM songs
WHERE id NOT IN (SELECT keep_id FROM keepers);
"""


def run():
    with engine.begin() as conn:
        result = conn.execute(text(REMAP_QUEUE))
        print(f"Remapped {result.rowcount} queue_registrations rows to keeper song")

        result = conn.execute(text(REMAP_SHEETS))
        print(f"Remapped {result.rowcount} song_sheets rows to keeper song")

        result = conn.execute(text(REMAP_LYRICS))
        print(f"Remapped {result.rowcount} song_lyrics rows to keeper song")

        result = conn.execute(text(DELETE_DUPLICATES))
        print(f"Deleted {result.rowcount} duplicate songs")

    print("Deduplication complete.")


if __name__ == "__main__":
    run()