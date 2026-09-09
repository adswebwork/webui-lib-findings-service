import pytest

from app.ingest import dedupe_key

from .conftest import audit, finding

# No module-level asyncio mark: asyncio_mode = auto collects the async tests on its own,
# and a blanket mark would also land on the sync dedupe-key tests at the bottom.


async def test_first_run_accepts_everything(client):
    r = await client.post(
        "/v1/findings",
        json=audit(findings=[finding("#promo"), finding("#qty", "no label")]),
    )
    assert r.status_code == 200
    body = r.json()
    assert (body["accepted"], body["duplicates"], body["resolved"]) == (2, 0, 0)


async def test_identical_replay_is_a_noop(client):
    payload = audit(findings=[finding("#promo"), finding("#qty", "no label")])

    first = (await client.post("/v1/findings", json=payload)).json()
    second = (await client.post("/v1/findings", json=payload)).json()
    third = (await client.post("/v1/findings", json=payload)).json()

    assert first["accepted"] == 2
    # This is the property the whole design exists for: a client that retries because it
    # never saw the first response does not corrupt the store, and can tell from the
    # counts that its earlier call landed.
    assert second == third
    assert second["accepted"] == 0
    assert second["duplicates"] == 2

    report = (await client.get("/v1/findings/demo")).json()
    assert len(report["findings"]) == 2
    assert {f["seen_count"] for f in report["findings"]} == {3}


async def test_absent_finding_is_resolved_not_deleted(client):
    await client.post(
        "/v1/findings",
        json=audit(findings=[finding("#promo"), finding("#qty", "no label")]),
    )
    after_fix = (
        await client.post("/v1/findings", json=audit(findings=[finding("#qty", "no label")]))
    ).json()

    assert after_fix["resolved"] == 1
    assert after_fix["duplicates"] == 1

    report = (await client.get("/v1/findings/demo")).json()
    assert [f["locator"] for f in report["findings"]] == ["#qty"]
    assert report["counts"] == {"high": 1, "medium": 0, "low": 0}


async def test_regression_reopens_the_original_row(client):
    payload = audit(findings=[finding("#promo")])
    await client.post("/v1/findings", json=payload)
    await client.post("/v1/findings", json=audit(findings=[]))  # fixed

    assert (await client.get("/v1/findings/demo")).json()["findings"] == []

    again = (await client.post("/v1/findings", json=payload)).json()
    # Reopened, not re-created: the history of how often this has broken is the useful
    # part, and a new row would reset it to 1 every time somebody reintroduced the bug.
    assert again["accepted"] == 0
    assert again["duplicates"] == 1

    report = (await client.get("/v1/findings/demo")).json()
    assert report["findings"][0]["seen_count"] == 2


async def test_resolution_is_scoped_to_one_page_and_kind(client):
    await client.post("/v1/findings", json=audit(page="/cart", findings=[finding("#a")]))
    await client.post("/v1/findings", json=audit(page="/checkout", findings=[finding("#b")]))
    await client.post(
        "/v1/findings", json=audit(kind="seo", page="/cart", findings=[finding("#c", "no title")])
    )

    # A clean run of /cart's accessibility audit must not close /checkout's findings or
    # /cart's SEO findings -- the payload says nothing about either.
    await client.post("/v1/findings", json=audit(page="/cart", findings=[]))

    locators = {f["locator"] for f in (await client.get("/v1/findings/demo")).json()["findings"]}
    assert locators == {"#b", "#c"}


async def test_repeated_locator_within_one_batch_does_not_explode(client):
    # Postgres refuses to let one INSERT ... ON CONFLICT touch a row twice; a scanner
    # emitting the same locator twice must not become a 500.
    r = await client.post(
        "/v1/findings",
        json=audit(findings=[finding("#promo"), finding("#promo"), finding("#qty", "no label")]),
    )
    assert r.status_code == 200
    assert r.json()["accepted"] == 2


async def test_rule_rewording_updates_in_place(client):
    await client.post("/v1/findings", json=audit(findings=[finding("#promo", "old wording", "low")]))
    await client.post("/v1/findings", json=audit(findings=[finding("#promo", "new wording", "high")]))

    report = (await client.get("/v1/findings/demo")).json()
    assert len(report["findings"]) == 1
    assert report["findings"][0]["detail"] == "new wording"
    assert report["findings"][0]["severity"] == "high"


async def test_report_orders_by_severity(client):
    await client.post(
        "/v1/findings",
        json=audit(
            findings=[
                finding("#low", "minor", "low"),
                finding("#high", "serious", "high"),
                finding("#med", "middling", "medium"),
            ]
        ),
    )
    report = (await client.get("/v1/findings/demo")).json()
    assert [f["severity"] for f in report["findings"]] == ["high", "medium", "low"]


# --------------------------------------------------------------- validation

@pytest.mark.parametrize(
    "payload",
    [
        audit(kind="malware"),                      # kind outside the closed set
        audit(project="../../etc/passwd"),          # project name outside the pattern
        audit(project=""),                          # empty project
        audit(findings=[{"locator": "#a"}]),        # detail missing
        audit(findings=[finding("#a", severity="critical")]),  # severity outside the set
        audit(findings=[{"locator": "#a", "detail": "d", "surprise": 1}]),  # unknown field
    ],
)
async def test_bad_payloads_fail_closed(client, payload):
    r = await client.post("/v1/findings", json=payload)
    assert r.status_code == 422


async def test_oversized_report_is_rejected_not_truncated(client):
    # Truncating would make the page look better than it is, and the resolution pass
    # would then close findings that are still real.
    too_many = [finding(f"#n{i}") for i in range(501)]
    r = await client.post("/v1/findings", json=audit(findings=too_many))
    assert r.status_code == 422
    assert "at most 500" in r.text


async def test_rate_limit_returns_429_with_retry_after(client, monkeypatch):
    from app.ratelimit import limiter

    monkeypatch.setattr(limiter, "limit", 3)
    for _ in range(3):
        assert (await client.post("/v1/findings", json=audit())).status_code == 200

    r = await client.post("/v1/findings", json=audit())
    assert r.status_code == 429
    assert int(r.headers["Retry-After"]) >= 1

    # Budget is per project, so a noisy project cannot starve a quiet one.
    other = await client.post("/v1/findings", json=audit(project="other"))
    assert other.status_code == 200


async def test_healthz_checks_the_database(client):
    r = await client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "database": "ok"}


# ------------------------------------------------------------- the key itself

def test_dedupe_key_is_not_ambiguous_across_field_boundaries():
    # Without a separator these collide, and two unrelated findings become one row.
    assert dedupe_key("ab", "ada", "/p", "#x") != dedupe_key("a", "bada", "/p", "#x")


def test_dedupe_key_is_stable():
    assert dedupe_key("demo", "ada", "/checkout", "#promo") == dedupe_key(
        "demo", "ada", "/checkout", "#promo"
    )
