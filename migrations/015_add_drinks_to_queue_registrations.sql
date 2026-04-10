ALTER TABLE queue_registrations ADD COLUMN IF NOT EXISTS drinks text[] DEFAULT '{}';
