-- Audit log table for tracking entity mutations (registrations, users)
CREATE TABLE IF NOT EXISTS audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_type VARCHAR NOT NULL,           -- 'registration' | 'user'
    action VARCHAR NOT NULL,                -- 'create' | 'update' | 'delete'
    actor_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    entity_id UUID NOT NULL,
    mac_address VARCHAR,
    before JSONB,
    after JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_audit_logs_entity_type   ON audit_logs(entity_type);
CREATE INDEX IF NOT EXISTS idx_audit_logs_action        ON audit_logs(action);
CREATE INDEX IF NOT EXISTS idx_audit_logs_entity_id     ON audit_logs(entity_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_actor_user_id ON audit_logs(actor_user_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_created_at    ON audit_logs(created_at DESC);
