"""
Migration: move lyrics/sheet data from songs table into song_lyrics and song_sheets.
Run once after 001_create_tables.sql has been executed.

Usage:
    cd lyric360_backend
    python -m migrations.002_migrate_data
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import text
from database import engine


MIGRATE_SHEETS = """
INSERT INTO song_sheets (song_id, sheet_drive_url, tone_male, tone_female, created_at)
SELECT id, sheet_drive_url, tone_male, tone_female, created_at
FROM songs
WHERE sheet_drive_url IS NOT NULL AND sheet_drive_url <> '';
"""

MIGRATE_LYRICS = """
INSERT INTO song_lyrics (song_id, lyrics, slide_drive_url, created_at)
SELECT id, lyrics, slide_drive_url, created_at
FROM songs
WHERE lyrics IS NOT NULL AND lyrics <> '';
"""

def run():
    with engine.begin() as conn:
        result_sheets = conn.execute(text(MIGRATE_SHEETS))
        print(f"Migrated {result_sheets.rowcount} rows into song_sheets")

        result_lyrics = conn.execute(text(MIGRATE_LYRICS))
        print(f"Migrated {result_lyrics.rowcount} rows into song_lyrics")

    print("Migration complete.")

if __name__ == "__main__":
    run()