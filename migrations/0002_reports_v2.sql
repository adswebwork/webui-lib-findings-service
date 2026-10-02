-- v2 contract: stable issue identity (rule_id), report-level idempotency, ordering via a
-- lockable scope row, and explicit scan status. v1 tables are untouched; legacy rows are
-- not copied because they carry no rule_id and one must not be invented for them.

-- A scope is the unit a complete report is authoritative for. Its row is locked
-- (SELECT ... FOR UPDATE) while a report is applied, which serialises reports per scope.
CREATE TABLE scopes (
    id                  BIGSERIAL PRIMARY KEY,
    project             VARCHAR(128) NOT NULL,
    source              VARCHAR(64)  NOT NULL,
    category            VARCHAR(32)  NOT NULL,
    page                VARCHAR(500) NOT NULL,
    ruleset             VARCHAR(500) NOT NULL,
    last_scanned_at     TIMESTAMPTZ,            -- newest APPLIED complete report
    last_attempt_at     TIMESTAMPTZ,            -- newest non-stale report of any status
    last_attempt_status VARCHAR(16),
    UNIQUE (project, source, category, page, ruleset)
);

CREATE TABLE reports (
    id             BIGSERIAL PRIMARY KEY,
    report_id      VARCHAR(128) NOT NULL,
    project        VARCHAR(128) NOT NULL,
    scope_id       BIGINT NOT NULL REFERENCES scopes (id),
    scan_id        VARCHAR(128),
    payload_digest VARCHAR(64) NOT NULL,
    status         VARCHAR(16) NOT NULL,        -- complete | partial | failed
    scanned_at     TIMESTAMPTZ NOT NULL,
    received_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    outcome        VARCHAR(16) NOT NULL,        -- applied | stale | not_applied
    result         JSONB NOT NULL,
    UNIQUE (project, report_id)
);
CREATE INDEX ix_reports_scope_time ON reports (scope_id, scanned_at);

CREATE TABLE issues (
    id                 BIGSERIAL PRIMARY KEY,
    issue_key          VARCHAR(64) NOT NULL UNIQUE,
    scope_id           BIGINT NOT NULL REFERENCES scopes (id),
    project            VARCHAR(128) NOT NULL,
    source             VARCHAR(64)  NOT NULL,
    category           VARCHAR(32)  NOT NULL,
    page               VARCHAR(500) NOT NULL,
    rule_id            VARCHAR(128) NOT NULL,
    locator            VARCHAR(500) NOT NULL DEFAULT '',
    detail             TEXT NOT NULL,
    severity           VARCHAR(16) NOT NULL,
    evidence           JSONB NOT NULL DEFAULT '{}'::jsonb,
    help_url           VARCHAR(500),
    observation_count  INTEGER NOT NULL DEFAULT 1,  -- distinct applied reports
    first_seen_at      TIMESTAMPTZ NOT NULL,
    last_seen_at       TIMESTAMPTZ NOT NULL,
    resolved_at        TIMESTAMPTZ
);
CREATE INDEX ix_issues_project_state ON issues (project, resolved_at);
CREATE INDEX ix_issues_scope_open ON issues (scope_id, resolved_at);
