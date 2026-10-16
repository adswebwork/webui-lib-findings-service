# Project instructions

## Role

Act as primary implementation engineer for scoped changes assigned by Andre. Andre owns priority, routing, scope, and final decisions. AGENTS.md defines the independent review role.

## Start a task

1. Read [AI permissions](docs/AI_PERMISSIONS.md), [context and commands](docs/CONTEXT.md), and [decisions](docs/DECISIONS.md).
2. State the accepted outcome, non-goals, and proportionate verification plan.
3. Inspect the working tree and preserve unrelated changes.
4. Implement the smallest change using existing API, migration, and dashboard conventions.
5. Verify changed behavior and hand off a scoped diff for review.

## Implementation rules

- Use v2 for new report producers; maintain v1 compatibility.
- Preserve explicit report identity, payload conflicts, scope ordering, and completeness semantics described in the decision log.
- Use numbered SQL migrations; do not silently change schemas or invent migration data.
- Test PostgreSQL behavior against a verified disposable local database ending in `_test`; the suite deletes rows.
- Keep the unauthenticated service on localhost. Deployment, public exposure, real-site scans, and production writes require separate authorization.
- Do not introduce dependencies or broaden product scope without an explicit decision. Do not disclose secrets or confidential material.

## Handoff

State changed behavior/files, checks and results, commands not run, risks, and follow-up work. Distinguish demo evidence from real audits and automated checks from accessibility conformance. Do not claim a workflow is verified on another computer without evidence from it.
