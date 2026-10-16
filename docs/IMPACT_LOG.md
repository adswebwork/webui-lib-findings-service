# Impact log

Entries follow the ai-operating-system Impact Log procedure and entry template. Ranges do not overlap. Add a new entry below the last one; correct an earlier entry rather than duplicating it.

## 2026-09-09 to 2026-10-11

Sources checked: `origin/main` history, PR and issue lists, GitHub Actions runs, on 2026-10-16. Prepared by: Claude Code.

### Shipped

| Shipped | Result | Beneficiary | Evidence | Next step |
| --- | --- | --- | --- | --- |
| Findings service v1: idempotent ingestion of scanner findings, FastAPI + PostgreSQL | CI passed on the merge commit | Andre, as developer of the checker pipeline | `433e10e`; CI on `main`, 2026-09-09 | Superseded by v2 below |
| CI against a Postgres 16 service container, CI badge, MIT license | CI passed on each commit | Andre; future contributors | `4d5b7b8`, `a01239f`, `1318e75`; CI on `main`, 2026-09-09 | None |
| v2 reports contract (report and issue identity, replay/409, scope ordering, completeness), a11y-audit adapter, read-only dashboard, numbered migrations | CI passed on the merge commit. On 2026-10-16 the same application code passed 45 local tests against Postgres, and the service answered `/healthz` and served `/dashboard` on loopback | Andre; checker producers that adopt v2 (no adopters measured) | `9b1b121`; CI on `main`, 2026-10-02; `docs/CONTEXT.md` verification record in [PR #1](https://github.com/adswebwork/webui-lib-findings-service/pull/1) | Real-scanner end-to-end run once a11y-audit is installed |

### Not shipped

Nothing open in this range. Pilot PR #1 was opened on 2026-10-12; see the next entry.

### Unmeasured

- No deployment exists, so there are no users or production results.
- The real-scanner walkthrough (`demo/e2e.py`) has not been run on this computer.
- Development time and any time saved were not recorded.

## 2026-10-12 to 2026-10-16

Sources checked: `origin/main` history, PR list, GitHub Actions runs, on 2026-10-16. Prepared by: Claude Code.

### Shipped

Nothing shipped in this range: no commits reached `main`.

### Not shipped

| Item | State | Evidence | Next step |
| --- | --- | --- | --- |
| AI permissions matrix and Context Pack (`AGENTS.md`, `CLAUDE.md`, `docs/CONTEXT.md`) | Open PR, CI passing, awaiting Andre's review | [PR #1](https://github.com/adswebwork/webui-lib-findings-service/pull/1) | Andre reviews and merges; Codex reads the pack |
| Review checklist, Self-Review trial record, `.gitignore` fix | Open PR stacked on #1, CI passing | [PR #2](https://github.com/adswebwork/webui-lib-findings-service/pull/2) | Merge after #1 |
| This impact log | Open PR | This branch | Andre reviews |

This range's work is documentation and AI-workflow setup only. No application behavior changed.

### Unmeasured

- Whether the context pack and checklist reduce onboarding or review effort for later sessions. The fresh-session handoff took about 110 seconds and the blind reviews about 1 minute each, but there is no manual baseline to compare.
- An open question from the Context Pack trial (health after a partial report) awaits Andre's decision; it is not a shipped fix.
