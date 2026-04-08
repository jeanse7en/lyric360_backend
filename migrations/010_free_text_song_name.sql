ALTER TABLE queue_registrations ALTER COLUMN song_id DROP NOT NULL;
ALTER TABLE queue_registrations ADD COLUMN IF NOT EXISTS free_text_song_name VARCHAR;
