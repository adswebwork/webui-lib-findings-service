# Decision log

Each entry: the decision, why, and what would change it. Status of everything below:
shipped and covered by tests unless marked **deferred**.

## 1. Add `/v2`; leave `/v1` untouched

`/v1` has no rule identity, no report identity, no ordering and treats an empty list as a
clean scan. Fixing those changes its meaning, so v2 is a new contract with new tables
(`scopes`, `reports`, `issues`). `/v1` keeps working and keeps its tests; it is legacy and
should not be used by new producers. **Legacy rows are not migrated**: they have no
`rule_id`, and inventing one would make them look scanner-sourced. *Change if:* a real v1
consumer with data worth keeping appears.

## 2. Issue identity

`issue_key = sha256(JSON[project, source, category, page, ruleset, rule_id, locator])`.

- `rule_id` is *what* is wrong, `locator` is *where*. Two rules on one element are two
  issues (previously the last one silently won).
- JSON array encoding is unambiguous for any field contents; a separator-joined string is
  not (a page or locator can contain the separator).
- `detail`, `severity`, evidence are not identity: rewording or rescoring updates the
  issue.
- `ruleset` is part of identity so each issue belongs to exactly one scope. Consequence:
  changing a checker's rule set starts new issues; the old ones stay open until that old
  ruleset is scanned again. Accepted: the alternative (resolving things nobody checked)
  is worse.
- Page canonicalisation is deliberately narrow: drop the fragment, lowercase scheme and
  host. Path and query are kept exactly, so `/a?x=1` and `/a?x=2` stay different pages.

## 3. Report identity and retries

The producer generates `report_id` once and reuses it on every retry. `UNIQUE(project,
report_id)` plus the SHA-256 of the normalised body: same id and body returns the stored
result (`replayed: true`, no writes, not rate-limited); same id with a different body is
`409`. A *new* scan gets a new id and counts as a new observation even if nothing
changed. `observation_count` therefore counts applied reports, never retries.

## 4. Ordering and concurrency

Scope = `(project, source, category, page, ruleset)`. A scope row is locked `FOR UPDATE`
while a report is applied (created first if absent, so the first report is serialised
too). Order is the producer's `scanned_at`; a complete report with `scanned_at <=` the
newest applied one is recorded as `stale` and does not change state (equal timestamps are
stale too, so ties are deterministic). Tested with concurrent deliveries against real
Postgres. Known limit: this trusts the producer's clock; it is single-producer-per-scope
safe, not a distributed ordering protocol.

## 5. Completeness

Only a `complete` report with an explicit `findings` list (`[]` for a clean scan) can
resolve issues. `partial` and `failed` reports are recorded and shown (project health
becomes `failed`), never applied. Oversized reports (>500 findings) are rejected, never
truncated or split. The adapter turns a scanner error or HTTP >= 400 into a `failed`
report, not an empty one.

## 6. History

Shipped: current state, first/last seen, `observation_count`, and a `reports` table with
one row per delivery. **Not shipped (deferred):** per-issue transition events, so no
fix-rate or time-to-fix metrics. `first_seen_at`/`resolved_at` are scan times, not
receipt times.

## 7. Migrations

Numbered SQL files in `migrations/`, applied once in order by `app/migrate.py`
(advisory-locked, one transaction per file, recorded in `schema_migrations`). Chosen over
Alembic to avoid a new dependency for this size; the cost is no autogeneration and no
downgrades. Tests run the real migrations, and one test checks models match the schema.
`0001` adopts an existing v1 database without touching its data. *Change if:* the schema
starts changing often.

## 8. Checker integration: `a11y-audit`

The only installed website checker is `a11y-audit` (plugin `engineering`, marketplace
`andre-skills`, i.e. a local directory, not the public Claude marketplace). Its
`scripts/scan.mjs` (axe-core via Playwright) is reused as-is; `tools/a11y_adapter.py`
maps `scan.json` to v2 reports. Mapping: one issue per axe rule per page, `locator ""`,
because `scan.json` keeps only the first 5 selectors per rule and per-element identity
would be incomplete; instance count and examples are evidence. Impact: critical/serious
-> high, moderate -> medium, minor -> low; anything else aborts the submission. "Needs
review" results are not reported. *Consequence:* an issue resolves only when a complete
scan finds zero instances of that rule on the page. *Change if:* `scan.mjs` is extended to
emit every element.

## 9. Dashboard: one static page, served by FastAPI

`app/static/dashboard.html`, vanilla JS, no build step, same origin (no CORS). Read-only.
Chosen for the smallest maintenance surface for a single-user demo. Scanned with
`a11y-audit` itself: 0 axe violations, no horizontal scroll at 320px, and its automated
Tab walk reached 11 controls, each with a visible focus indicator. That is automated
evidence only; no manual keyboard or screen reader pass was done. *Change if:* the UI needs routing, auth or heavy state.

## 10. Other fixes shipped

Compose binds Postgres to `127.0.0.1`; `/healthz` no longer returns driver error text;
`config.py` docstring matches its default; the test suite refuses to run unless the
database name ends in `_test`; the Docker image includes `migrations/`.

## Deferred / not done

Authentication and project authorization (a `project` string is not an access boundary;
do not expose this beyond localhost); dashboard-triggered scanning; manual
resolve/suppress; trends; Redis; multi-worker rate limiting; v1 removal.
