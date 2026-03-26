-- Step 1: Create song_sheets table
CREATE TABLE IF NOT EXISTS song_sheets (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    song_id     UUID NOT NULL REFERENCES songs(id) ON DELETE CASCADE,
    sheet_drive_url TEXT NOT NULL,
    tone_male   VARCHAR,
    tone_female VARCHAR,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_song_sheets_song_id ON song_sheets(song_id);

-- Step 2: Create song_lyrics table
CREATE TABLE IF NOT EXISTS song_lyrics (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    song_id         UUID NOT NULL REFERENCES songs(id) ON DELETE CASCADE,
    lyrics          TEXT NOT NULL,
    slide_drive_url TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_song_lyrics_song_id ON song_lyrics(song_id);