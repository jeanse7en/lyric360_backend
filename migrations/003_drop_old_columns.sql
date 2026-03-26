-- Step 3: Drop columns that have been moved to song_sheets and song_lyrics.
-- Run ONLY after 002_migrate_data.py has completed successfully.

ALTER TABLE songs
    DROP COLUMN IF EXISTS lyrics,
    DROP COLUMN IF EXISTS sheet_drive_url,
    DROP COLUMN IF EXISTS slide_drive_url,
    DROP COLUMN IF EXISTS tone_male,
    DROP COLUMN IF EXISTS tone_female;