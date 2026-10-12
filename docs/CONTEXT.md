# Context and commands

Inspected: 2026-10-12. Personal-project authorization: [AI permissions](AI_PERMISSIONS.md).

## Architecture map

- `app/main.py`: service lifecycle, legacy v1 endpoints, dashboard, health check.
- `app/api_v2.py`, `app/ingest_v2.py`, `app/schemas_v2.py`: v2 contract and report processing.
- `app/models.py`, `app/db.py`, `app/migrate.py`, `migrations/`: persistence and numbered migrations.
- `tools/a11y_adapter.py`: scanner output mapping; does not itself supply the external scanner.
- `app/static/dashboard.html`: read-only same-origin dashboard, no frontend build requirement.
- `tests/`: database integration, migrations, legacy/v2 behavior, and adapter coverage.
- `.github/workflows/ci.yml`: PostgreSQL 16 tests with Python 3.11 and a Docker image build.

The detailed invariants and deferred features live in [DECISIONS.md](DECISIONS.md). Report replay is scoped by project/report ID; payload mismatch conflicts. Scope rows lock ordering. Only a newer complete report resolves issues in the exact scope. Failed/partial/stale reports never resolve issues. Rule identity includes ruleset, while wording/severity/evidence are mutable.

## Commands and prerequisites

| Command | Purpose | Conditions / verification |
| --- | --- | --- |
| `python3.11 -m venv .venv` then `.venv/bin/pip install -r requirements.txt` | Dependency setup | Existing Python 3.11.11 environment found; dependency consistency checked separately. Do not recreate an active environment unnecessarily |
| `make test` | Start local PostgreSQL and run pytest | Docker daemon and verified disposable `_test` database required; database-backed execution blocked because Docker daemon was unavailable |
| `make run` | Run uvicorn on port 8000 | Docker required; uvicorn defaults to loopback. Startup not verified without database |
| `.venv/bin/python demo/e2e.py` | Local demo scanner walkthrough | Service running plus external a11y-audit scanner/Node required; not run |
| `make clean` | Remove Compose containers and volumes | Destructive; do not use as routine cleanup or delete data outside authorized disposable test resources |

The local Makefile contains uncommitted `setup` and `e2e` targets at inspection time. They are not part of this documentation change and must not be presented as committed commands until independently reviewed and committed. The README advertises those targets; use the direct commands above when the committed Makefile lacks them.

## Verification record

- Source/configuration inspection confirms Python/FastAPI/PostgreSQL structure, localhost database binding, destructive-test suffix guard, and CI commands.
- `make -n test run` checks command expansion only; it does not run tests or start the service.
- Docker daemon is unavailable. Database tests, service startup, Docker build, and real-scanner e2e remain unverified.
- External scanner installation and second-computer setup remain unverified.

## Fresh-session handoff exercise

For the second Context Pack trial, open a fresh session and ask it to explain what a partial report does, identify the relevant code/tests, propose a bounded verification plan, and name commands blocked by missing infrastructure. Compare its answer with the decision log and source; record actual results instead of treating this exercise definition as a completed trial.
