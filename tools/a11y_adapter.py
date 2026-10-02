"""Turn an a11y-audit `scan.json` into findings-service v2 reports, and optionally post them.

    python -m tools.a11y_adapter SCAN_JSON --project demo [--api http://127.0.0.1:8000]

Mapping (see docs/DECISIONS.md):
  * one report per scanned page; category "ada"; source "a11y-audit"
  * one issue per axe rule per page: rule_id = axe rule id, locator = "" (page-level).
    scan.json keeps only the first 5 element selectors per rule, so per-element identity
    would be incomplete; the instance count and examples travel as evidence instead.
  * a page that errored or returned HTTP >= 400 is a "failed" report, never a clean one
  * axe "needs review" results are not violations and are not reported
  * ruleset = the axe tag list, so changing the tags starts a new scope
  * report_id is derived from (project, scan time, url): re-running this on the same
    scan.json yields the same IDs, which is what makes re-posting safe
"""

import argparse
import hashlib
import json
import sys
import urllib.error
import urllib.request

SOURCE = "a11y-audit"
CATEGORY = "ada"
SEVERITY = {"critical": "high", "serious": "high", "moderate": "medium", "minor": "low"}


def to_reports(scan: dict, project: str) -> list[dict]:
    meta, tags = scan["meta"], sorted(scan["meta"]["tags"])
    ruleset = "axe:" + ",".join(tags)
    scan_id = hashlib.sha256(f'{project}|{meta["generated"]}'.encode()).hexdigest()[:24]
    reports, unmapped = [], set()
    for r in scan["results"]:
        report = {
            "report_id": hashlib.sha256(f'{project}|{meta["generated"]}|{r["url"]}'.encode()).hexdigest()[:32],
            "scan_id": scan_id,
            "project": project,
            "source": SOURCE,
            "category": CATEGORY,
            "page": r["url"],
            "ruleset": ruleset,
            "scanned_at": r["scannedAt"],
        }
        if r.get("error") or (r.get("status") or 0) >= 400 or "violations" not in r:
            reports.append({**report, "status": "failed", "findings": []})
            continue
        findings = []
        for v in r["violations"]:
            if v.get("impact") not in SEVERITY:
                unmapped.add(f'{v["id"]}: impact={v.get("impact")!r}')
                continue
            findings.append({
                "rule_id": v["id"],
                "locator": "",
                "detail": v["help"],
                "severity": SEVERITY[v["impact"]],
                "help_url": v.get("helpUrl"),
                "evidence": {
                    "instances": v["instances"],
                    "wcag": v.get("criteria", []),
                    "level": v.get("level"),
                    "examples": v.get("examples", []),
                    "axe_version": meta.get("axeVersion"),
                },
            })
        reports.append({**report, "status": "complete", "findings": findings})
    if unmapped:
        raise SystemExit("unmapped axe impact, refusing to submit: " + "; ".join(sorted(unmapped)))
    return reports


def post(api: str, report: dict) -> dict:
    req = urllib.request.Request(
        api.rstrip("/") + "/v2/reports",
        data=json.dumps(report).encode(),
        headers={"content-type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as e:
        raise SystemExit(f"{report['page']}: HTTP {e.code} {e.read().decode()[:300]}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("scan_json")
    ap.add_argument("--project", required=True)
    ap.add_argument("--api", help="base URL of the findings service; omit to print reports only")
    args = ap.parse_args(argv)
    reports = to_reports(json.load(open(args.scan_json)), args.project)
    if not args.api:
        print(json.dumps(reports, indent=2))
        return 0
    for rep in reports:
        res = post(args.api, rep)
        print(f'{rep["page"]}: {res["status"]} -> {res["outcome"]}'
              f'{" (replayed)" if res["replayed"] else ""} new={res["new"]} '
              f'seen_again={res["seen_again"]} reopened={res["reopened"]} resolved={res["resolved"]}')
    return 0


if __name__ == "__main__":
    sys.exit(main())
