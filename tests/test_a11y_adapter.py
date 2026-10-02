import copy
import json
from pathlib import Path

import pytest

from tools.a11y_adapter import to_reports

from .test_reports_v2 import post

FIXTURE = json.loads((Path(__file__).parent.parent / "demo/fixtures/scan-broken.json").read_text())


def test_maps_violations_one_issue_per_rule():
    [r] = to_reports(FIXTURE, "demo")
    assert (r["status"], r["category"], r["source"], r["page"]) == ("complete", "ada", "a11y-audit", FIXTURE["results"][0]["url"])
    assert sorted((f["rule_id"], f["severity"]) for f in r["findings"]) == [("image-alt", "high"), ("label", "high")]
    assert all(f["locator"] == "" and f["evidence"]["instances"] == 1 for f in r["findings"])


def test_ids_are_deterministic_for_one_scan_and_differ_between_scans():
    again = copy.deepcopy(FIXTURE)
    assert to_reports(FIXTURE, "demo")[0]["report_id"] == to_reports(again, "demo")[0]["report_id"]
    again["meta"]["generated"] = "2030-01-01T00:00:00.000Z"
    assert to_reports(FIXTURE, "demo")[0]["report_id"] != to_reports(again, "demo")[0]["report_id"]


def test_errored_or_http_error_pages_are_failed_not_clean():
    for patch in ({"error": "net::ERR_CONNECTION_REFUSED", "violations": None}, {"status": 404}):
        scan = copy.deepcopy(FIXTURE)
        scan["results"][0].update(patch)
        if "error" in patch:
            del scan["results"][0]["violations"]
        [r] = to_reports(scan, "demo")
        assert r["status"] == "failed" and r["findings"] == []


def test_unmapped_impact_refuses_to_submit():
    scan = copy.deepcopy(FIXTURE)
    scan["results"][0]["violations"][0]["impact"] = None
    with pytest.raises(SystemExit, match="unmapped"):
        to_reports(scan, "demo")


async def test_fixture_report_is_accepted_by_the_api_and_replays(client):
    [r] = to_reports(FIXTURE, "demo")
    first = await post(client, r)
    assert first.status_code == 200 and first.json()["new"] == 2
    assert (await post(client, r)).json()["replayed"] is True
