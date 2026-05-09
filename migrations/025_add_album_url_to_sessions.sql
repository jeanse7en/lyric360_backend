ALTER TABLE live_sessions
    ADD COLUMN IF NOT EXISTS album_url TEXT;
