ALTER TABLE queue_registrations
    ADD COLUMN IF NOT EXISTS preorder_number INTEGER;
