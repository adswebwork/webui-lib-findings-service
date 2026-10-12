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

Owner authorization is explicit and consistent with repository constraints. Docker was unavailable during initial verification, so no database tests or local service startup were performed. The `_test` suffix is necessary but does not replace checking resource identity and disposability.

Next permitted action: complete repository context documentation and command discovery, then run tests when a disposable local database is available. Revisit this matrix if data, services, or actions change.
