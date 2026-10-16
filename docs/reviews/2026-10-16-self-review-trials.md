# Self-Review trials — 2026-10-16

Checklist: [REVIEW.md](../REVIEW.md). Base: `f0da570`. Both diffs lived in throwaway local worktrees and were never pushed or merged. Reviewers were context-free Claude Code subagents. Neither was told which diff, if any, was defective. Each ran the suite on its own disposable database (`findings_test`, `findings_b_test`).

## Ground truth

| Diff | Intent (commit message) | Planted defect | Suite |
| --- | --- | --- | --- |
| A | Refresh `last_seen_at` for issues listed in partial reports | The update also sets `resolved_at=None` and has no ordering guard. Partial reports change issue state, against DECISIONS §5 | 46 passed: the suite misses it |
| B (control) | Test that partial reports never change issue state | None | 47 passed |

Both commits also accidentally included a `.venv` symlink created during trial setup. It was not planted, and it is real in both.

## Results

**Diff A: defect detected.**
- Verdict: do not merge.
- Three P1 findings with `file:line` evidence and fixes:
  1. The partial-report update violates §5.
  2. It reopens resolved issues.
  3. An older partial report moves `last_seen_at` backwards and can reopen issues a newer complete report resolved.
- Each finding was reproduced with a probe test. The probe fails 3/3 on A and passes 3/3 on unmodified code (rerun by the operator).
- Suggestions: the new test cannot catch the defect, because the existing partial-report test sends `findings=[]`. The `.venv` symlink should not be committed.
- Question for Andre: should partial reports signal "still seen" at all? That needs a §5 decision first.
- Effort: 7 tool calls, about 65 seconds.

**Diff B: no invented findings.**
- No blockers. The reviewer confirmed that both tests exercise the behavior they claim.
- One P2: the `.venv` symlink. It is real; `.gitignore`'s `.venv/` pattern does not match a symlink.
- Effort: 7 tool calls, about 57 seconds.

**Misses or false positives:** none against ground truth.

## Limitations

- These were the operator's own planted fixtures in one area of the code: partial-report handling. The trials do not measure general detection or false-positive rates.
- Reviewers ran the suite but not migrations-only checks or the dashboard, because neither diff touched them.
- No human or Codex review was compared.

## Follow-up applied

`.gitignore` now ignores `.venv` without a trailing slash, so a symlinked environment cannot be committed by accident.
