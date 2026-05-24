-- Add columns that existed in Supabase DB but were missing from SQLAlchemy models.
-- Safe to run multiple times (IF NOT EXISTS).

ALTER TABLE live_sessions
    ADD COLUMN IF NOT EXISTS presenting_lyric_url TEXT;

ALTER TABLE queue_registrations
    ADD COLUMN IF NOT EXISTS actual_tone VARCHAR,
    ADD COLUMN IF NOT EXISTS note TEXT,
    ADD COLUMN IF NOT EXISTS rating INTEGER;
