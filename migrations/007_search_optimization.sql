-- Enable pg_trgm for fast substring search (no unaccent needed)
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Add normalized column for accent-insensitive Vietnamese search
-- Python will populate this with diacritics stripped (e.g. "Mưa" → "mua", "Đường" → "duong")
ALTER TABLE songs ADD COLUMN IF NOT EXISTS title_normalized TEXT;

-- Drop old basic index
DROP INDEX IF EXISTS ix_songs_title;

-- Index on normalized title for fast trigram substring search
CREATE INDEX IF NOT EXISTS ix_songs_title_normalized
    ON songs USING gin(title_normalized gin_trgm_ops);

-- Also keep a plain index on title for exact/prefix lookups
CREATE INDEX IF NOT EXISTS ix_songs_title
    ON songs (lower(title));