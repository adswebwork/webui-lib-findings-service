import hashlib

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from .models import AuditRun, Finding
from .schemas import AuditIn, IngestResult


def dedupe_key(project: str, kind: str, page: str, locator: str) -> str:
    """sha256(project | kind | page | locator).

    The separator matters. Joined naively, ('ab', 'c') and ('a', 'bc') hash the same and
    two unrelated findings collapse into one row. Not theoretical -- locators and page
    paths are both arbitrary text.

    sha256 rather than the sha1 the PHP version started with. This is not a security
    boundary, but there is no reason to leave a weak hash in a service whose job is
    reporting security-adjacent findings.
    """
    return hashlib.sha256(
        "\x1f".join([project, kind, page, locator]).encode("utf-8")
    ).hexdigest()


async def ingest(session: AsyncSession, payload: AuditIn) -> IngestResult:
    """Idempotent ingest of one audit run.

    Three things happen in one transaction:

      1. every finding is upserted on its dedupe key
      2. anything previously open for this (project, kind, page) and absent from this
         payload is marked resolved
      3. the run itself is recorded

    Step 2 is why this endpoint takes a whole report rather than one finding at a time.
    A single finding tells you something is wrong; only the complete set for a page
    tells you what is no longer wrong, and that is the half most ingestion paths omit.
    """
    # Collapse duplicates inside the batch before they reach Postgres. Two rows in one
    # INSERT ... ON CONFLICT that resolve to the same key raise "cannot affect row a
    # second time" -- a 500 on what is really just a scanner reporting one element
    # twice. Dedupe here and the same payload is merely idempotent.
    rows: dict[str, dict] = {}
    for item in payload.findings:
        key = dedupe_key(payload.project, payload.kind.value, payload.page, item.locator)
        rows[key] = {
            "dedupe_key": key,
            "project": payload.project,
            "kind": payload.kind.value,
            "page": payload.page,
            "locator": item.locator,
            "detail": item.detail,
            "severity": item.severity.value,
            "seen_count": 1,
        }

    accepted = 0
    duplicates = 0

    if rows:
        stmt = insert(Finding).values(list(rows.values()))
        stmt = stmt.on_conflict_do_update(
            index_elements=[Finding.dedupe_key],
            set_={
                "seen_count": Finding.__table__.c.seen_count + 1,
                "last_seen": func.now(),
                # detail and severity are properties of the finding, not part of its
                # identity, so a reworded or rescored rule updates the row it already
                # owns instead of orphaning it.
                "detail": stmt.excluded.detail,
                "severity": stmt.excluded.severity,
                # A finding that comes back after being fixed reopens, rather than
                # staying closed behind a stale resolution date.
                "resolved_at": None,
            },
        ).returning(Finding.seen_count)

        # seen_count comes back post-update: 1 means this statement inserted the row,
        # anything higher means it already existed. One round trip for the whole report,
        # and no read-before-write -- the SQLite version needed a SELECT per finding
        # because it cannot tell you which branch fired.
        result = await session.execute(stmt)
        for (count,) in result.all():
            if count == 1:
                accepted += 1
            else:
                duplicates += 1

    # Close out what this page no longer reports.
    still_open = await session.execute(
        select(Finding.dedupe_key).where(
            Finding.project == payload.project,
            Finding.kind == payload.kind.value,
            Finding.page == payload.page,
            Finding.resolved_at.is_(None),
        )
    )
    gone = [key for (key,) in still_open.all() if key not in rows]

    resolved = 0
    if gone:
        await session.execute(
            update(Finding)
            .where(Finding.dedupe_key.in_(gone))
            .values(resolved_at=func.now())
        )
        resolved = len(gone)

    session.add(
        AuditRun(
            project=payload.project,
            kind=payload.kind.value,
            page=payload.page,
            submitted=len(payload.findings),
            accepted=accepted,
            duplicates=duplicates,
            resolved=resolved,
        )
    )

    await session.commit()

    return IngestResult(
        project=payload.project,
        kind=payload.kind,
        page=payload.page,
        submitted=len(payload.findings),
        accepted=accepted,
        duplicates=duplicates,
        resolved=resolved,
    )
