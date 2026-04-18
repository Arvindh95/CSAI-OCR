-- CSAI-OCR Phase 9 — template editor schema
-- Applied manually. Idempotent guards on CREATE TABLE to allow re-runs.

-- Templates: one row per (doc_type_code, version). Only one active version per code.
CREATE TABLE IF NOT EXISTS doc_templates (
    id              SERIAL PRIMARY KEY,
    client_id       INT REFERENCES clients(id) ON DELETE CASCADE, -- NULL = global
    name            TEXT NOT NULL,
    doc_type_code   TEXT NOT NULL,              -- stable slug clients send in doc_type param
    version         INT NOT NULL DEFAULT 1,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_by      TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_doc_templates_active_code
    ON doc_templates(doc_type_code) WHERE is_active;
CREATE UNIQUE INDEX IF NOT EXISTS idx_doc_templates_code_version
    ON doc_templates(doc_type_code, version);
CREATE INDEX IF NOT EXISTS idx_doc_templates_client
    ON doc_templates(client_id) WHERE client_id IS NOT NULL;

-- Per-page sample images + dims (multi-page support)
CREATE TABLE IF NOT EXISTS template_pages (
    template_id    INT NOT NULL REFERENCES doc_templates(id) ON DELETE CASCADE,
    page_index     INT NOT NULL,                -- 0-based
    image_path     TEXT NOT NULL,               -- /opt/ocr-saas/templates/{template_id}/page_{n}.jpg
    image_width    INT NOT NULL,
    image_height   INT NOT NULL,
    PRIMARY KEY (template_id, page_index)
);

-- Fields: each pinned to a page (page_index) within its template
CREATE TABLE IF NOT EXISTS template_fields (
    id             SERIAL PRIMARY KEY,
    template_id    INT NOT NULL REFERENCES doc_templates(id) ON DELETE CASCADE,
    field_name     TEXT NOT NULL,               -- "invoice_no", "total_amount"
    page_index     INT NOT NULL DEFAULT 0,      -- which page this field lives on
    strategy       TEXT NOT NULL CHECK (strategy IN ('anchor','zone','regex')),
    config         JSONB NOT NULL,              -- strategy-specific payload
    post_process   TEXT,                        -- date | number | uppercase | trim | NULL
    required       BOOLEAN NOT NULL DEFAULT FALSE,
    display_order  INT NOT NULL DEFAULT 0
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_template_fields_unique
    ON template_fields(template_id, field_name);
CREATE INDEX IF NOT EXISTS idx_template_fields_template_page
    ON template_fields(template_id, page_index);

-- Per-client whitelist: which templates a client may use via doc_type param
CREATE TABLE IF NOT EXISTS client_templates (
    client_id    INT NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    template_id  INT NOT NULL REFERENCES doc_templates(id) ON DELETE CASCADE,
    granted_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (client_id, template_id)
);
CREATE INDEX IF NOT EXISTS idx_client_templates_template
    ON client_templates(template_id);

-- Jobs: track which template version ran (for reproducibility)
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS template_id INT REFERENCES doc_templates(id);
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS template_version INT;
CREATE INDEX IF NOT EXISTS idx_jobs_template ON jobs(template_id) WHERE template_id IS NOT NULL;
