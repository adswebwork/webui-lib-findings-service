# Findings service

[![CI](https://github.com/adswebwork/webui-lib-findings-service/actions/workflows/ci.yml/badge.svg)](https://github.com/adswebwork/webui-lib-findings-service/actions/workflows/ci.yml)

**A website issue tracker that receives automated check results, remembers recurring
problems, and shows developers what still needs fixing.** FastAPI + PostgreSQL.

It does not inspect websites itself. It sits between a checker and a dashboard:

    website -> checker (a11y-audit) -> adapter -> FastAPI -> PostgreSQL -> dashboard

## An example

A check of `/checkout` reports an image with no alt text and an unlabeled input. The
service stores both as open issues. Run the check again and the same two issues are
updated, not duplicated. Fix the image and run a *complete* new check: that issue moves
to resolved. Break it again and it reopens. A failed check, an older report arriving late,
or a half-finished scan never makes the project look healthier than it is.

Open the dashboard at `http://127.0.0.1:8000/dashboard` to see current issues, filter and
sort them, and inspect the evidence the checker supplied.

## What is included

| Piece | Where | Status |
|---|---|---|
| API (v2) and database | `app/`, `migrations/` | shipped, tested |
| Legacy API (v1) | `app/main.py` | kept for compatibility; not for new use |
| Checker adapter | `tools/a11y_adapter.py` | shipped; maps `a11y-audit` output |
| Dashboard (read-only) | `app/static/dashboard.html` | shipped |
| Real-scanner walkthrough | `demo/e2e.py` | shipped |
| Demo pages and a sample scan | `demo/pages/`, `demo/fixtures/` | **demo data**, not a client audit |

External dependency: the **`a11y-audit` skill** (plugin `engineering`, from the local
`andre-skills` marketplace) supplies `scan.mjs`, which needs Node and a one-time
`bash <skill>/scripts/setup.sh` install of Playwright and axe-core. Not included here.

## Setup

Prerequisites: Python 3.11, Docker, and (for real scans) Node.

```bash
make setup   # creates .venv, installs dependencies
make test    # starts Postgres (docker compose) and runs the suite
make run     # service on http://127.0.0.1:8000, API docs at /docs
```

First real scan, in a second terminal (scans only a page the script serves locally):

```bash
make e2e     # scan -> submit -> retry -> fix -> reopen -> stale -> failed
```

Then open `http://127.0.0.1:8000/dashboard?project=portfolio-demo`. To submit your own
scan: run `scan.mjs` on a page you are authorized to test, then

```bash
.venv/bin/python -m tools.a11y_adapter path/to/scan.json --project my-site --api http://127.0.0.1:8000
```

Postgres listens on `127.0.0.1:55432`. Set `FINDINGS_DATABASE_URL` to override (see
`.env.example`). The service has **no authentication**: keep it on localhost.

## Key concepts

- **Issue**: one rule failing on one page (optionally at one locator). Identity ignores
  wording and severity, so rescoring a rule updates the issue rather than duplicating it.
- **Report**: one delivery from a checker for one page. The producer chooses a
  `report_id` once and reuses it on retries; replays are free and change nothing.
- **Scope**: (project, source, category, page, ruleset). A *complete* report is
  authoritative for its scope only: it resolves what it no longer lists, and nothing else.
- **Complete / partial / failed**: only `complete` can resolve issues. The others are
  recorded and surfaced as project health `failed`.
- **Stale**: a complete report not newer than the last applied one is recorded, not applied.

Example request and response:

```bash
curl -s localhost:8000/v2/reports -H 'content-type: application/json' -d '{
  "report_id": "scan-2026-10-02-checkout", "project": "shop", "source": "a11y-audit",
  "category": "ada", "page": "https://shop.example/checkout", "ruleset": "axe:wcag2a",
  "status": "complete", "scanned_at": "2026-10-02T15:00:00Z",
  "findings": [{"rule_id": "image-alt", "detail": "Images must have alternative text", "severity": "high"}]
}'
# {"report_id":"scan-2026-10-02-checkout","status":"complete","outcome":"applied",
#  "applied":true,"replayed":false,"new":1,"seen_again":0,"reopened":0,"resolved":0,...}
```

| Endpoint | Purpose |
|---|---|
| `POST /v2/reports` | submit a report (`409` on id reuse with different content, `429` over budget) |
| `GET /v2/projects` | projects with open counts and health |
| `GET /v2/projects/{p}` | project detail and per-page latest check |
| `GET /v2/projects/{p}/issues` | filter by state/severity/category/source/page/rule; sort; `limit`/`offset` |
| `GET /v2/issues/{id}` | one issue with evidence |
| `GET /dashboard` | the dashboard |
| `GET /healthz` | liveness plus a database check |

## Architecture

FastAPI owns the contract and domain rules; PostgreSQL owns persistence **and** ordering.
Idempotency is a unique constraint, ordering is a row lock on the scope, and issue upserts
are one `INSERT ... ON CONFLICT` per report. Reasoning for each choice, and what would
change it, is in [docs/DECISIONS.md](docs/DECISIONS.md). Schema changes are numbered SQL
files in `migrations/`, applied automatically at startup.

## Tests

```bash
make test
```

Runs against real PostgreSQL (the suite uses `ON CONFLICT`, row locks and `jsonb`). It
refuses to run unless the database name ends in `_test`, because it deletes all rows.
Covered: identity, replay and conflict, concurrent delivery, resolve/reopen, stale,
failed/partial/oversized, scope boundaries, filtering/pagination/counts, migrations from
a v1-only database, and the adapter mapping. CI runs the suite against a `postgres:16`
service container and builds the image.

## Limitations

- No authentication or authorization; `project` is just a string. Localhost only.
- No per-issue event history, so no fix-rate or time-to-fix. `observation_count` counts
  applied reports only.
- The a11y adapter reports one issue per rule per page: `scan.json` keeps only the first
  5 element selectors per rule. An issue resolves when a complete scan finds none of that
  rule on the page.
- Ordering trusts the producer's `scanned_at`.
- Changing a ruleset starts new issues; old ones stay open until that ruleset is rescanned.
- Automated accessibility checks find only part of real problems. Nothing here is a
  conformance or compliance claim.
- Rate limiting is per process. v1 data is not migrated into v2.
- Deferred: dashboard-triggered scans, manual resolve/suppress, trends, Redis, v1 removal.
