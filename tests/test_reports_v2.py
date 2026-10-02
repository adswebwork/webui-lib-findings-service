import asyncio

from app.schemas_v2 import canonical_page, issue_key

T1, T2, T3 = "2026-10-01T10:00:00Z", "2026-10-01T11:00:00Z", "2026-10-01T12:00:00Z"


def f(rule="image-alt", locator="", sev="high", detail="Images must have alternative text"):
    return {"rule_id": rule, "locator": locator, "detail": detail, "severity": sev}


def report(rid, at=T1, findings=(), status="complete", page="/checkout", project="demo",
           ruleset="wcag2a", **kw):
    body = {
        "report_id": rid, "project": project, "source": "a11y-audit", "category": "ada",
        "page": page, "ruleset": ruleset, "status": status, "scanned_at": at,
    }
    if findings is not None:
        body["findings"] = list(findings)
    return {**body, **kw}


async def post(client, body):
    return await client.post("/v2/reports", json=body)


async def issues(client, project="demo", **params):
    return (await client.get(f"/v2/projects/{project}/issues", params=params)).json()


# --- identity -------------------------------------------------------------------------

async def test_two_rules_at_one_locator_stay_separate(client):
    await post(client, report("r1", findings=[f("image-alt", "#hero"), f("color-contrast", "#hero")]))
    page = await issues(client)
    assert page["total"] == 2
    assert {i["rule_id"] for i in page["items"]} == {"image-alt", "color-contrast"}


async def test_reworded_or_rescored_issue_keeps_identity(client):
    await post(client, report("r1", T1, [f(sev="low", detail="old wording")]))
    await post(client, report("r2", T2, [f(sev="high", detail="new wording")]))
    page = await issues(client)
    assert page["total"] == 1
    item = page["items"][0]
    assert (item["severity"], item["detail"], item["observation_count"]) == ("high", "new wording", 2)


def test_issue_key_is_unambiguous_and_page_canonicalisation_is_narrow():
    assert issue_key("p", "s", "ada", "/", "w", "a", "bc") != issue_key("p", "s", "ada", "/", "w", "ab", "c")
    assert issue_key("p", "s", "ada", "/", "w", "r\x1fx", "") != issue_key("p", "s", "ada", "/", "w", "r", "x")
    assert issue_key("p", "s", "ada", "/", "w1", "r", "") != issue_key("p", "s", "ada", "/", "w2", "r", "")
    assert canonical_page("HTTPS://Example.com/a?x=1#top") == "https://example.com/a?x=1"
    assert canonical_page("/a?x=1") != canonical_page("/a?x=2")
    assert canonical_page("/checkout") == "/checkout"


# --- retries --------------------------------------------------------------------------

async def test_exact_replay_is_a_noop(client):
    body = report("r1", findings=[f()])
    first = (await post(client, body)).json()
    second = (await post(client, body)).json()
    assert first["new"] == 1 and first["replayed"] is False
    assert second["replayed"] is True and second["new"] == 1  # stored result, unchanged
    assert (await issues(client))["items"][0]["observation_count"] == 1


async def test_report_id_reuse_with_different_body_is_409(client):
    await post(client, report("r1", findings=[f()]))
    r = await post(client, report("r1", findings=[f(), f("label")]))
    assert r.status_code == 409
    assert (await issues(client))["total"] == 1


async def test_new_report_id_with_same_findings_counts_a_new_observation(client):
    await post(client, report("r1", T1, [f()]))
    r = (await post(client, report("r2", T2, [f()]))).json()
    assert r["seen_again"] == 1 and r["new"] == 0
    assert (await issues(client))["items"][0]["observation_count"] == 2


async def test_concurrent_identical_deliveries_record_one_observation(client):
    body = report("r1", findings=[f()])
    results = await asyncio.gather(*[post(client, body) for _ in range(8)])
    assert {r.status_code for r in results} == {200}
    assert sum(1 for r in results if not r.json()["replayed"]) == 1
    assert (await issues(client))["items"][0]["observation_count"] == 1


async def test_replay_is_not_rate_limited(client):
    from app.ratelimit import limiter
    body = report("r1", findings=[f()])
    await post(client, body)
    limiter.limit = 1  # budget already spent by the first delivery
    try:
        assert (await post(client, body)).status_code == 200
        assert (await post(client, report("r2", T2, [f()]))).status_code == 429
    finally:
        from app.config import settings
        limiter.limit = settings.rate_limit_requests


# --- resolve / reopen -----------------------------------------------------------------

async def test_complete_scan_resolves_then_reintroduction_reopens(client):
    await post(client, report("r1", T1, [f("image-alt"), f("label")]))
    fixed = (await post(client, report("r2", T2, [f("label")]))).json()
    assert fixed["resolved"] == 1
    assert (await issues(client))["total"] == 1
    assert (await issues(client, state="resolved"))["items"][0]["rule_id"] == "image-alt"

    back = (await post(client, report("r3", T3, [f("image-alt"), f("label")]))).json()
    assert back["reopened"] == 1
    page = await issues(client)
    assert page["total"] == 2
    assert {i["rule_id"]: i["observation_count"] for i in page["items"]} == {"image-alt": 2, "label": 3}


async def test_explicit_empty_complete_scan_resolves(client):
    await post(client, report("r1", T1, [f()]))
    r = (await post(client, report("r2", T2, []))).json()
    assert r["resolved"] == 1 and r["applied"] is True


# --- completeness / staleness ---------------------------------------------------------

async def test_missing_findings_on_complete_report_is_rejected(client):
    r = await post(client, report("r1", findings=None))
    assert r.status_code == 422


async def test_oversized_report_is_rejected_and_resolves_nothing(client):
    await post(client, report("r1", T1, [f()]))
    big = [f(f"rule-{i}") for i in range(501)]
    assert (await post(client, report("r2", T2, big))).status_code == 422
    assert (await issues(client))["total"] == 1


async def test_failed_and_partial_reports_never_resolve_or_look_healthier(client):
    await post(client, report("r1", T1, [f()]))
    for rid, status in (("r2", "failed"), ("r3", "partial")):
        r = (await post(client, report(rid, T2, [], status=status))).json()
        assert r["outcome"] == "not_applied" and r["resolved"] == 0
    assert (await issues(client))["total"] == 1
    project = (await client.get("/v2/projects/demo")).json()
    assert project["health"] == "failed"
    assert project["scope_list"][0]["last_attempt_status"] == "partial"
    # a later complete scan restores the state
    await post(client, report("r4", T3, [f()]))
    assert (await client.get("/v2/projects/demo")).json()["health"] == "issues"


async def test_stale_report_cannot_replace_newer_state(client):
    await post(client, report("new", T2, [f("label")]))
    old = (await post(client, report("old", T1, [f("image-alt")]))).json()
    assert old["outcome"] == "stale" and old["applied"] is False
    page = await issues(client)
    assert [i["rule_id"] for i in page["items"]] == ["label"]
    # equal timestamp with a different report is also not applied (deterministic tie-break)
    tie = (await post(client, report("tie", T2, []))).json()
    assert tie["outcome"] == "stale"
    assert (await issues(client))["total"] == 1


async def test_stale_failed_report_does_not_overwrite_scope_status(client):
    await post(client, report("r2", T2, []))
    await post(client, report("old-fail", T1, [], status="failed"))
    assert (await client.get("/v2/projects/demo")).json()["health"] == "clean"


async def test_concurrent_different_reports_for_one_scope_are_deterministic(client):
    bodies = [report(f"r{i}", f"2026-10-01T10:0{i}:00Z", [f(f"rule-{i}")]) for i in range(6)]
    await asyncio.gather(*[post(client, b) for b in bodies])
    page = await issues(client)
    # newest report wins regardless of arrival order
    assert [i["rule_id"] for i in page["items"]] == ["rule-5"]
    assert (await client.get("/v2/projects/demo")).json()["scope_list"][0]["last_scanned_at"].startswith("2026-10-01T10:05")


async def test_resolution_does_not_cross_scope_boundaries(client):
    await post(client, report("a", T1, [f()], page="/cart"))
    await post(client, report("b", T1, [f()], page="/checkout"))
    await post(client, report("c", T1, [f()], project="other"))
    await post(client, report("d", T1, [f()], ruleset="wcag21aa"))  # other ruleset, same page
    await post(client, report("e", T2, [], page="/cart"))
    assert (await issues(client, page="/cart", state="resolved"))["total"] == 1
    assert (await issues(client, page="/checkout"))["total"] == 2  # both rulesets untouched
    assert (await issues(client, project="other"))["total"] == 1


# --- read API -------------------------------------------------------------------------

async def test_filters_counts_pagination_and_stable_order(client):
    fs = [f(f"r{i:02d}", sev=("high", "medium", "low")[i % 3]) for i in range(7)]
    await post(client, report("r1", T1, fs))
    full = await issues(client, limit=3)
    assert full["total"] == 7 and full["counts"] == {"high": 3, "medium": 2, "low": 2}
    ids = []
    for off in (0, 3, 6):
        ids += [i["id"] for i in (await issues(client, limit=3, offset=off))["items"]]
    assert len(ids) == len(set(ids)) == 7
    only_high = await issues(client, severity="high", limit=2)
    assert only_high["total"] == 3 and len(only_high["items"]) == 2
    assert only_high["counts"] == full["counts"]  # counts cover the set, not the page
    sevs = [i["severity"] for i in (await issues(client))["items"]]
    assert sevs == sorted(sevs, key=("high", "medium", "low").index)


async def test_project_health_states_and_issue_detail(client):
    assert (await client.get("/v2/projects/ghost")).status_code == 404
    await post(client, report("r1", T1, [f(evidence={"instances": 3}) if False else {**f(), "evidence": {"instances": 3}}]))
    assert (await client.get("/v2/projects")).json()[0]["health"] == "issues"
    iid = (await issues(client))["items"][0]["id"]
    detail = (await client.get(f"/v2/issues/{iid}")).json()
    assert detail["evidence"] == {"instances": 3} and detail["state"] == "open"
    await post(client, report("r2", T2, []))
    assert (await client.get("/v2/projects")).json()[0]["health"] == "clean"
    assert (await client.get("/v2/issues/99999")).status_code == 404
