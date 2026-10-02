-- Baseline of the v1 schema that create_all() used to build. IF NOT EXISTS so existing
-- local databases adopt the migration runner without data loss.
CREATE TABLE IF NOT EXISTS findings (
    id           BIGSERIAL PRIMARY KEY,
    dedupe_key   VARCHAR(64) NOT NULL UNIQUE,
    project      VARCHAR(128) NOT NULL,
    kind         VARCHAR(32) NOT NULL,
    page         VARCHAR(500) NOT NULL,
    locator      VARCHAR(500) NOT NULL,
    detail       TEXT NOT NULL,
    severity     VARCHAR(16) NOT NULL DEFAULT 'low',
    seen_count   INTEGER NOT NULL DEFAULT 1,
    first_seen   TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen    TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at  TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS ix_findings_project_open ON findings (project, resolved_at, severity);
CREATE INDEX IF NOT EXISTS ix_findings_run_scope ON findings (project, kind, page, resolved_at);

CREATE TABLE IF NOT EXISTS audit_runs (
    id          BIGSERIAL PRIMARY KEY,
    project     VARCHAR(128) NOT NULL,
    kind        VARCHAR(32) NOT NULL,
    page        VARCHAR(500) NOT NULL,
    submitted   INTEGER NOT NULL DEFAULT 0,
    accepted    INTEGER NOT NULL DEFAULT 0,
    duplicates  INTEGER NOT NULL DEFAULT 0,
    resolved    INTEGER NOT NULL DEFAULT 0,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_audit_runs_project_time ON audit_runs (project, created_at);
