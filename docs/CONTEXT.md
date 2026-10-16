# Context and commands

Inspected: 2026-10-12; commands re-verified 2026-10-16. Personal-project authorization: [AI permissions](AI_PERMISSIONS.md).

## Architecture map

- `app/main.py`: service lifecycle, legacy v1 endpoints, dashboard, health check.
- `app/api_v2.py`, `app/ingest_v2.py`, `app/schemas_v2.py`: v2 contract and report processing.
- `app/models.py`, `app/db.py`, `app/migrate.py`, `migrations/`: persistence and numbered migrations.
- `tools/a11y_adapter.py`: scanner output mapping; does not itself supply the external scanner.
- `app/static/dashboard.html`: read-only same-origin dashboard, no frontend build requirement.
- `tests/`: database integration, migrations, legacy/v2 behavior, and adapter coverage.
- `.github/workflows/ci.yml`: PostgreSQL 16 tests with Python 3.11 and a Docker image build.

The detailed invariants and deferred features live in [DECISIONS.md](DECISIONS.md). Report replay is scoped by project/report ID; payload mismatch conflicts. Scope rows lock ordering. Only a complete report newer than the scope's last *applied* complete report (`last_scanned_at`) resolves issues, and only in its exact scope. Failed/partial/stale reports never resolve issues.

Behavior confirmed in code but not stated in DECISIONS.md (`app/ingest_v2.py:91-112`, `app/api_v2.py:60-75`):

- Partial and failed reports are recorded as `not_applied`, never `stale`, and count against the rate limit. Findings sent on a partial report are validated and counted in `submitted`, then ignored.
- Project health is `failed` when any scope's latest attempt (`last_attempt_status`) is failed or partial, even if other scopes are clean.
- Open question for Andre (no test covers it): a complete report dated after the last applied complete report but before a later partial report is applied and resolves issues, yet the scope keeps `last_attempt_status = partial`, so health stays `failed`. A partial report with the same `scanned_at` as the last complete report also flips health to `failed`. Rule identity includes ruleset, while wording/severity/evidence are mutable.

## Commands and prerequisites

| Command | Purpose | Conditions / verification |
| --- | --- | --- |
| `python3.11 -m venv .venv` then `.venv/bin/pip install -r requirements.txt` | Dependency setup | 2026-10-16: existing `.venv` (Python 3.11.11); `pip install -r requirements.txt` and `pip check` clean. Do not recreate an active environment unnecessarily |
| `make test` | Start local PostgreSQL and run pytest | Docker daemon and verified disposable `_test` database required. 2026-10-16: 45 passed against `findings_test` on `127.0.0.1:55432` |
| `make run` | Run uvicorn on port 8000 | Docker required. `make run` binds loopback, but the `Dockerfile` starts uvicorn on `0.0.0.0`: publish a container port only as `127.0.0.1:<port>`. 2026-10-16: listened on `127.0.0.1:8000` only; `/healthz` returned `{"status":"ok","database":"ok"}`, `/dashboard` 200; stopped after the check |
| `.venv/bin/python demo/e2e.py` | Local demo scanner walkthrough | Service running plus external a11y-audit `scan.mjs` (found via `A11Y_SCAN` or the `~/.claude/plugins/cache` glob in `demo/e2e.py`) and Node. Not run: scanner not installed on this computer as of 2026-10-16 |
| `make clean` | Remove Compose containers and volumes | Destructive; do not use as routine cleanup or delete data outside authorized disposable test resources |

The local Makefile contains uncommitted `setup` and `e2e` targets at inspection time. They are not part of this documentation change and must not be presented as committed commands until independently reviewed and committed. The README advertises those targets; use the direct commands above when the committed Makefile lacks them.

## Verification record

- Source/configuration inspection confirms Python/FastAPI/PostgreSQL structure, localhost database binding, destructive-test suffix guard, and CI commands.
- 2026-10-12: Docker daemon was unavailable; only `make -n test run` (command expansion) was checked.
- 2026-10-16: dependency install, `make test` (45 passed), and `make run` with health/dashboard probes verified on loopback. README endpoints match the routes in `app/main.py` and `app/api_v2.py`; migrations are `0001_legacy_v1.sql` and `0002_reports_v2.sql`.
- Docker image build is exercised by CI only; not run locally. Real-scanner e2e remains unverified.
- External scanner installation and second-computer setup remain unverified.

## Fresh-session handoff trial

2026-10-16, Claude Code subagent with no prior context, read-only, base `1f69062`. Prompt: explain what a partial report does, cite code and tests, propose a bounded verification plan, and name blocked commands.

- Result: correct explanation with file:line citations, matching `app/ingest_v2.py` and `tests/test_reports_v2.py::test_failed_and_partial_reports_never_resolve_or_look_healthier` on spot-check. Its verification plan respected the `_test` guard, excluded `make clean`, and named Docker and the external scanner as prerequisites.
- Effort: about 110 seconds, 10 tool calls, about 22 files opened. Beyond these docs it needed four source/test files: `app/ingest_v2.py`, `app/api_v2.py`, `app/schemas_v2.py`, and `tests/test_reports_v2.py`.
- Corrections it surfaced, now applied above: this file still said Docker was unavailable; "newer complete report" was ambiguous; the Dockerfile's `0.0.0.0` binding was not flagged; partial-report details were undocumented. It also found the untested edge case listed as an open question.
- Not changed: DECISIONS.md wording (owner decision), product behavior, and untracked `node_modules/` and `yarn.lock` in the working tree (origin unknown, not part of this pack).
