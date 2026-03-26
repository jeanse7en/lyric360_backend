-- Add presenting_lyric_url to live_sessions so the musician can push
-- the current lyric to the singer's screen in real-time.
ALTER TABLE live_sessions
    ADD COLUMN IF NOT EXISTS presenting_lyric_url TEXT;
