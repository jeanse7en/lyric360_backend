-- Add verified_at to song_sheets and song_lyrics.
-- NULL = AI-ingested but not yet reviewed by a musician.
ALTER TABLE song_sheets  ADD COLUMN IF NOT EXISTS verified_at TIMESTAMPTZ;
ALTER TABLE song_lyrics  ADD COLUMN IF NOT EXISTS verified_at TIMESTAMPTZ;