-- CSAI-OCR initial billing schema
-- Applied manually once; subsequent changes via alembic revisions.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Clients
CREATE TABLE clients (
    id              SERIAL PRIMARY KEY,
    name            TEXT NOT NULL,
    email           TEXT NOT NULL UNIQUE,
    api_key_hash    BYTEA NOT NULL UNIQUE,
    api_key_prefix  TEXT NOT NULL,
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_clients_api_key_hash ON clients(api_key_hash);
CREATE INDEX idx_clients_active ON clients(is_active) WHERE is_active;

-- Plans (one active row per client; history via effective_to)
CREATE TABLE plans (
    id                   SERIAL PRIMARY KEY,
    client_id            INT REFERENCES clients(id) ON DELETE CASCADE,
    max_transactions     INT NOT NULL DEFAULT 2000,
    max_pages_per_txn    INT NOT NULL DEFAULT 1,
    reset_period         TEXT NOT NULL DEFAULT 'monthly',
    effective_from       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    effective_to         TIMESTAMPTZ
);
CREATE UNIQUE INDEX idx_plans_current ON plans(client_id) WHERE effective_to IS NULL;

-- Periods (explicit rollover tracking)
CREATE TABLE periods (
    id              BIGSERIAL PRIMARY KEY,
    client_id       INT REFERENCES clients(id) ON DELETE CASCADE,
    period_start    TIMESTAMPTZ NOT NULL,
    period_end      TIMESTAMPTZ NOT NULL,
    is_open         BOOLEAN NOT NULL DEFAULT TRUE
);
CREATE UNIQUE INDEX idx_periods_open ON periods(client_id) WHERE is_open;
CREATE INDEX idx_periods_client_range ON periods(client_id, period_start DESC);

-- Jobs
CREATE TABLE jobs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id       INT REFERENCES clients(id),
    period_id       BIGINT REFERENCES periods(id),
    endpoint        TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'queued',
    pages_submitted INT NOT NULL DEFAULT 1,
    attempts        INT NOT NULL DEFAULT 0,
    idempotency_key TEXT,
    body_hash       BYTEA,
    input_meta      JSONB,
    result          JSONB,
    error_msg       TEXT,
    queued_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,
    ip_address      INET
);
CREATE INDEX idx_jobs_client ON jobs(client_id, queued_at DESC);
CREATE INDEX idx_jobs_status ON jobs(status) WHERE status IN ('queued','processing');
CREATE INDEX idx_jobs_period ON jobs(period_id);
CREATE UNIQUE INDEX idx_jobs_idempotency ON jobs(client_id, idempotency_key)
    WHERE idempotency_key IS NOT NULL;

-- Audit log (admin actions)
CREATE TABLE audit_log (
    id           BIGSERIAL PRIMARY KEY,
    timestamp    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source_ip    INET,
    method       TEXT NOT NULL,
    path         TEXT NOT NULL,
    actor_note   TEXT,
    request_body JSONB,
    status_code  INT
);
CREATE INDEX idx_audit_time ON audit_log(timestamp DESC);

-- Usage log (ledger)
CREATE TABLE usage_log (
    id              BIGSERIAL PRIMARY KEY,
    client_id       INT REFERENCES clients(id),
    period_id       BIGINT REFERENCES periods(id),
    job_id          UUID REFERENCES jobs(id),
    pages           INT NOT NULL DEFAULT 1,
    status          TEXT NOT NULL,
    reject_reason   TEXT,
    response_ms     INT,
    timestamp       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_usage_client_time ON usage_log(client_id, timestamp DESC);
CREATE INDEX idx_usage_period ON usage_log(period_id);

-- Monthly billing summary
CREATE TABLE billing_summary (
    id                    SERIAL PRIMARY KEY,
    client_id             INT REFERENCES clients(id),
    period_id             BIGINT REFERENCES periods(id) UNIQUE,
    period_start          DATE NOT NULL,
    period_end            DATE NOT NULL,
    total_transactions    INT DEFAULT 0,
    total_pages           INT DEFAULT 0,
    rejected_transactions INT DEFAULT 0,
    error_transactions    INT DEFAULT 0,
    generated_at          TIMESTAMPTZ DEFAULT NOW()
);
