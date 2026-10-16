# AI permissions

Reviewed: 2026-10-12. Status: confirmed for the actions below. Decision owner: Andre.

## Sources

- Andre explicitly confirmed in the AI Operating System planning chat on 2026-10-12: this is his personal project with no employer/client-confidential material; Claude Code and Codex may read/edit code, run local tests against a disposable database ending in `_test`, and create branches and PRs. Deployment, public exposure, real-site scans, and production data changes need separate authorization.
- Repository constraints: [README](../README.md), [decision log](DECISIONS.md), `tests/conftest.py`, and `docker-compose.yml`. The service has no authentication; tests delete rows.

## Matrix

| Material / action | Service/environment | State | Conditions |
| --- | --- | --- | --- |
| Personal-project code and related prompts | Claude Code / Codex | Allowed | Scope is this project; no employer/client-confidential material |
| Synthetic/demo scan evidence | Claude Code / Codex | Allowed | Existing personal-project demo data only; classify newly supplied evidence before use |
| Secrets in Git, prompts, or logs | Either tool | Prohibited | Keep credentials in approved local storage; do not disclose them |
| Repository reads, dependency retrieval, branch/PR writes | Project Git remote / package sources | Allowed within task | Minimum material necessary for authorized code and local-test work; no private-data upload to unrelated services |
| Third-party AI services or private-data uploads elsewhere | Other accounts/destinations | Unresolved | Not covered by the selected-tool authorization |
| Local tests | Disposable local database ending in `_test` | Allowed | Verify target identity and disposability before execution; tests delete all rows |
| Local service operation | Loopback | Allowed within local verification | Bind to localhost; do not expose publicly |
| Deployment/public exposure | Hosting or non-loopback interface | Requires separate authorization | Not authorized by this matrix |
| Real-site scans | Non-demo targets | Requires separate authorization | Confirm target and permission to scan |
| Production data writes | Production resources | Requires separate authorization | Local test permission does not cover production |
| Messages, unrelated external writes | External recipients/resources | Unresolved | Branch/PR permission does not authorize unrelated actions |

## Verification and limitations

Owner authorization is explicit and consistent with repository constraints. The `_test` suffix is necessary but does not replace checking resource identity and disposability.

- 2026-10-12: Docker was unavailable; no database tests or local service startup were performed.
- 2026-10-16 (Claude Code, base `5044b75`): target identity checked before execution — `findings_test` on the project's own `docker-compose.yml` Postgres, published on `127.0.0.1:55432` only, throwaway local credentials, `FINDINGS_DATABASE_URL` unset so the `conftest.py` default applied. `make test`: 45 passed in 3.8s (about 9.5s including container start). Local service startup and real scans were not exercised.

Next permitted action: use this matrix for Context Pack, Self-Review, Impact Log, and Scope Guard work on this repository. Revisit it if data, services, or actions change.
