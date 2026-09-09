# Findings service

Idempotent ingestion for scanner findings. FastAPI + Postgres.

Scanners produce the same finding over and over: they re-run on every build, they retry
when the network drops, and a developer re-runs them repeatedly while fixing what they
reported. An ingestion path that treats each arrival as new turns one problem into
hundreds of rows within a day, and the dashboard on top of it stops being readable.

This service takes a whole scan report, writes it idempotently, and closes out what the
scan no longer reports. It is small on purpose -- three endpoints -- and the README
argues the design decisions rather than just listing them.

It began as a port of a PHP endpoint in a local development console, which received the
CSS-budget, accessibility and SEO findings an in-browser audit tool produced per page.
That version runs against SQLite on one developer's machine and is fine there. This
exists because the same design has to hold when the producers are many, the store is
shared, and callers retry.

```bash
make db      # postgres on :55432 via docker compose
make test    # integration suite against real postgres
make run     # uvicorn on :8000, docs at /docs
```

## The endpoints

| | |
|---|---|
| `POST /v1/findings` | ingest one audit run; safe to retry |
| `GET /v1/findings/{project}` | open findings, worst first, plus severity counts |
| `GET /healthz` | liveness plus a real database check |

## The design

### Ingest is idempotent, and the key is the whole thing

```
dedupe_key = sha256(project | kind | page | locator)
```

with a unique constraint behind it. Every write is `INSERT ... ON CONFLICT (dedupe_key)
DO UPDATE`, so a repeat arrival bumps `seen_count` and `last_seen` instead of adding a
row.

This is not defensive coding for a rare case. The same finding arrives repeatedly by
design: the console re-audits on every page load, the browser retries on network
failure, and a developer hits `audit` over and over while fixing a page. Without the
key, one problem becomes hundreds of rows inside a day and the dashboard stops being
readable — which is the actual failure mode, not data loss.

Three details worth the space:

- **The separator is load-bearing.** Joined naively, `("ab", "c")` and `("a", "bc")`
  hash the same. Locators and page paths are both arbitrary text, so that collision is
  reachable, not theoretical. Fields are joined on `\x1f`.
- **`detail` and `severity` are deliberately not in the key.** They are properties of a
  finding, not its identity. If a rule gets reworded or rescored, that has to update the
  row it already owns rather than orphan it and open a new one.
- **sha256, not the sha1 the PHP started with.** Not a security boundary, but there is
  no reason to leave a weak hash in a service whose job is reporting security-adjacent
  findings.

### The response tells a retrying client what its retry did

```json
{"submitted": 3, "accepted": 0, "duplicates": 3, "resolved": 1}
```

A client that never saw the first response can tell from `accepted: 0` that its earlier
call landed. That is what makes the endpoint genuinely safe to retry rather than merely
non-destructive.

### Resolution, not deletion

Most ingestion paths stop at dedupe and have no answer for *what happens when the
finding goes away*. Here the endpoint takes a whole report rather than one finding at a
time, precisely so it can answer that: anything previously open for this
`(project, kind, page)` and absent from the payload is marked `resolved_at` — not
deleted.

That keeps two questions answerable that a delete would destroy: what this page used to
get wrong, and the fix rate over time. It also means a regression **reopens the original
row** rather than creating a new one, so `seen_count` stays an honest record of how often
something has broken.

Scoping matters here. A clean run of `/cart`'s accessibility audit must not close
`/checkout`'s findings or `/cart`'s SEO findings — the payload says nothing about
either. There is a test for exactly this.

### Validation fails closed

Pydantic models are `extra="forbid"` with closed enums for `kind` and `severity` and a
pattern on `project`. A scanner that starts sending a field we do not store gets told,
instead of us silently dropping data someone believes is being recorded.

Oversized reports are **rejected, not truncated**. Truncating would make a page look
better than it is, and then the resolution pass would close findings that are still
real — a silent correctness bug produced by a well-meant limit.

### Backpressure returns 429, never drops

A page erroring in a loop, or a scanner wired into hot reload, can post continuously.
The write budget is **per project** so one noisy project cannot starve the rest, and
over-budget requests get `429` with `Retry-After` rather than a discarded report — for
the same reason as above: to the caller, a dropped report is indistinguishable from a
page that got better.

### One statement per report

The upsert is a single batched `INSERT ... ON CONFLICT ... RETURNING seen_count` for the
whole report. `seen_count` comes back post-update, so `1` means this statement inserted
the row and anything higher means it already existed — new versus repeat, with no
read-before-write. The SQLite version needs a `SELECT` per finding because it cannot
tell you which branch fired.

One consequence: Postgres refuses to let a single `ON CONFLICT` statement touch the same
row twice, so a scanner emitting one locator twice would be a 500. Duplicates are
collapsed within the batch before the statement is built.

## Where Redis goes

It isn't here, and that is a decision rather than an omission. At one developer box with
a handful of scanners, an in-process sliding window and a synchronous write are the
right size, and adding a queue would buy latency and an at-least-once delivery problem
in exchange for nothing.

Two things change that, and they are different problems:

1. **More than one worker.** The rate limiter is in-process, so running two workers
   doubles the effective limit. The counter has to move to Redis — `INCR` with a TTL, or
   a token bucket in a Lua script for exactness — before the budget means anything.
2. **Bursts outrunning the write path.** Ingest becomes an enqueue, workers drain. That
   makes delivery at-least-once, which is only safe because the write is already
   idempotent: at-least-once delivery plus idempotent writes is effectively
   exactly-once, and the dedupe key is what buys that.

A short-TTL cache on `GET /v1/findings/{project}` is the third use, and the least
interesting — the dashboard polls the same rollup repeatedly and the data tolerates
being a few seconds stale.

## Where this would need more work

Stated plainly rather than left for someone to discover:

- **Migrations.** `create_all` is for local development and tests. It cannot express the
  column changes and backfills a live table needs; a real deployment gets Alembic.
- **Partitioning.** `findings` grows with pages × rules × projects. The read path is
  almost entirely "open findings for one project", so partitioning by project (or time,
  for `audit_runs`) is the scale step. Not warranted at this size.
- **AuthN/AuthZ.** There is none. The PHP version is loopback-only via `guard.php`;
  this service assumes it sits behind something. Anything multi-tenant needs a real
  identity on the request, because `project` is currently a caller-supplied string and
  nothing stops one project writing findings under another's name.
- **`GET` has no pagination beyond a capped `limit`.** Fine for a dashboard showing the
  worst 200; not fine as an export path.

## Tests

The suite runs against real Postgres, on purpose. An in-memory SQLite substitute would
not exercise `ON CONFLICT ... RETURNING`, `array_position`, or timezone-aware
timestamps — which is most of what there is to get wrong here.
