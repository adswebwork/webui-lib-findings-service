# Review checklist

Project adaptation of Quality Gate Review from ai-operating-system (`codex/skills/quality-gate-review/SKILL.md`). It applies to both a self-review by the implementer and an independent review. Read [AI permissions](AI_PERMISSIONS.md), [context and commands](CONTEXT.md), and [decisions](DECISIONS.md) first.

## Inputs

- A scoped diff, for example `git diff <base>...HEAD`.
- The accepted outcome or acceptance criteria. If none are supplied, say so and review against the decision log.
- The verified commands in [CONTEXT.md](CONTEXT.md).

## Invariants to check against changed behavior

Cite the [decision log](DECISIONS.md) section when a finding rests on one.

| Area | Check | Decision |
| --- | --- | --- |
| Identity | `issue_key` fields unchanged; detail/severity/evidence stay mutable; ruleset stays in identity | §2 |
| Idempotency | Same `report_id` + body replays with no writes and no rate-limit charge; different body is 409; `observation_count` counts applied reports only | §3 |
| Ordering/concurrency | Scope row locked `FOR UPDATE` before any state change; complete reports with `scanned_at <=` last applied are stale; attempt status never moves backwards in time | §4 |
| Scope resolution | Resolution and reopening touch only issues in the report's exact scope | §2, §4 |
| Completeness | Failed/partial/stale/oversized reports change no issue state: no insert, reopen, resolve, or `last_seen_at`/count update; health must not look better than reality | §5 |
| Migrations | New numbered SQL file; existing files unchanged; `tests/test_migrations.py` against real PostgreSQL | §7 |
| v1 | Legacy `/v1` behavior and tests unchanged | §1 |

Also check that each new test actually exercises the claimed behavior. A test can pass while the diff breaks an invariant it never checks.

## Dashboard changes

When `app/static/dashboard.html` changes:

- Keep rendering through `textContent`/attributes, never `innerHTML` with API data. Fetch only same-origin.
- Keep keyboard operation, visible focus, the `aria-pressed`, `aria-live`, and `role="status"` patterns, labelled regions, and contrast.
- Report anything checked by hand as observed behavior. Automated checks do not establish accessibility conformance.

## Checks

Run what the diff warrants and is permitted by [AI permissions](AI_PERMISSIONS.md):

- `make test`, or `.venv/bin/pytest -q`, against a verified disposable database ending in `_test`. Use a separate `_test` database when two reviews run at once.
- Focused tests: `.venv/bin/pytest -q tests/<file> -k <expr>`.
- Read-only inspection: `git diff`, `grep`.

Record the checks you did not run, and why. Do not run `make clean`, deploy, or scan real sites.

## Output

1. **Blockers:** must fix before merge. These are invariant violations, data loss, security issues, or a failing check.
2. **Suggestions:** non-blocking improvements.
3. **Questions:** facts or decisions the reviewer cannot settle; Andre decides.
4. **Verification:** checks run with results, checks not run, and limitations.

Each finding gives severity (P1 blocker, P2 should fix, P3 suggestion), `file:line`, evidence (code, a test, or a reproduction), operational impact, and a concrete fix. A clean diff may have no findings. Do not invent findings to fill a review.
