"""End-to-end walkthrough: real a11y-audit scans of a local demo page -> adapter -> API.

    make db && make run          # in another terminal (service on :8000, dev database)
    python demo/e2e.py           # needs node, a11y-audit deps (see README) and the service

Scans only a page this script serves from 127.0.0.1. Asserts each step and exits non-zero
on the first surprise. Safe to re-run: every scan gets fresh report IDs.
"""
import glob
import http.server
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from tools.a11y_adapter import post, to_reports  # noqa: E402

API = os.environ.get("FINDINGS_API", "http://127.0.0.1:8000")
PROJECT = os.environ.get("DEMO_PROJECT", "portfolio-demo")
PORT = 8765
SCAN = os.environ.get("A11Y_SCAN") or next(iter(sorted(glob.glob(
    os.path.expanduser("~/.claude/plugins/cache/*/engineering/*/skills/a11y-audit/scripts/scan.mjs")))), None)
if not SCAN:
    sys.exit("a11y-audit scan.mjs not found; set A11Y_SCAN=/path/to/scan.mjs")

site = Path(tempfile.mkdtemp())
URL = f"http://127.0.0.1:{PORT}/checkout.html"
handler = lambda *a, **k: http.server.SimpleHTTPRequestHandler(*a, directory=str(site), **k)  # noqa: E731
http.server.ThreadingHTTPServer.allow_reuse_address = True
server = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), handler)
threading.Thread(target=server.serve_forever, daemon=True).start()


def get(path):
    with urllib.request.urlopen(API + path, timeout=10) as r:
        return json.load(r)


def open_rules():
    items = get(f"/v2/projects/{PROJECT}/issues?state=open&limit=200")["items"]
    return {i["rule_id"]: i["observation_count"] for i in items}


def step(n, title):
    print(f"\n[{n}] {title}")


def check(cond, msg):
    print(("  ok   " if cond else "  FAIL ") + msg)
    if not cond:
        sys.exit(1)


def scan(page_file, label):
    """Run the real scanner against the served page and return the parsed scan.json."""
    if page_file:
        shutil.copy(ROOT / "demo/pages" / page_file, site / "checkout.html")
    else:
        (site / "checkout.html").unlink(missing_ok=True)  # server answers 404
    out = site / f"scan-{label}"
    subprocess.run(["node", SCAN, "--out", str(out), URL], check=True, capture_output=True)
    return json.loads((out / "scan.json").read_text())


def submit(scan_json):
    return [post(API, r) for r in to_reports(scan_json, PROJECT)]


step(1, "scan the page with two known problems and submit it")
first = scan("broken.html", "1")
[res] = submit(first)
check(res["outcome"] == "applied" and res["new"] == 2, f"applied, 2 new issues ({res})")
check(set(open_rules()) == {"image-alt", "label"}, "dashboard API lists image-alt and label")
check(set(open_rules().values()) == {1}, "each issue observed once")

step(2, "retry the same report")
[res] = submit(first)
check(res["replayed"] is True, "service reports it as a replay")
check(set(open_rules().values()) == {1}, "observation counts not inflated")

step(3, "fix the image, run a new complete scan")
[res] = submit(scan("image-fixed.html", "3"))
check(res["resolved"] == 1, "one issue resolved")
check(set(open_rules()) == {"label"}, "only the unlabeled input remains open")
resolved = get(f"/v2/projects/{PROJECT}/issues?state=resolved")["items"]
check([i["rule_id"] for i in resolved] == ["image-alt"], "image-alt is listed as resolved")

step(4, "reintroduce the problem")
[res] = submit(scan("broken.html", "4"))
check(res["reopened"] == 1, "image-alt reopened")
check(set(open_rules()) == {"image-alt", "label"}, "both open again")
before = open_rules()

step(5, "deliver an older report (re-labelled as a new delivery)")
older = json.loads(json.dumps(first))
older["meta"]["generated"] = "2020-01-01T00:00:00.000Z"  # fresh IDs, original scan times
[res] = submit(older)
check(res["outcome"] == "stale" and res["applied"] is False, "recorded as stale, not applied")

step(6, "deliver a failed check (page now answers 404)")
time.sleep(1.1)
[res] = submit(scan(None, "6"))
check(res["status"] == "failed" and res["resolved"] == 0, "failed report resolves nothing")
check(open_rules() == before, "open issues and counts unchanged")
check(get(f"/v2/projects/{PROJECT}")["health"] == "failed", "project health says failed, not clean")

step(7, "restore the page and confirm recovery")
[res] = submit(scan("broken.html", "7"))
check(get(f"/v2/projects/{PROJECT}")["health"] == "issues", "health back to issues")

print(f"\nAll checks passed. Open http://127.0.0.1:8000/dashboard?project={PROJECT}")
server.shutdown()
