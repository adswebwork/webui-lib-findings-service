from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Issue, Report, Scope
from .schemas_v2 import ReportIn, ReportResult, issue_key


class ReportConflict(Exception):
    """Same (project, report_id) re-sent with different content."""


class RateLimited(Exception):
    def __init__(self, retry_after: int) -> None:
        self.retry_after = retry_after


def _replay(existing: Report, digest: str) -> ReportResult:
    if existing.payload_digest != digest:
        raise ReportConflict(existing.report_id)
    return ReportResult(**{**existing.result, "replayed": True})


async def _find(session: AsyncSession, project: str, report_id: str) -> Report | None:
    return await session.scalar(
        select(Report).where(Report.project == project, Report.report_id == report_id)
    )


async def ingest_report(session: AsyncSession, payload: ReportIn, charge) -> ReportResult:
    """Apply one report. `charge(project)` -> (allowed, retry_after) is consulted only for
    reports not already stored, so a retry of a delivered report is never rate limited.

    Ordering and concurrency: the scope row is locked FOR UPDATE for the rest of the
    transaction, so reports for one scope apply one at a time, including the first report
    for a scope that has no rows yet (the row is created, then locked). Reports for other
    scopes do not contend.
    """
    digest = payload.digest()

    existing = await _find(session, payload.project, payload.report_id)
    if existing:
        return _replay(existing, digest)

    allowed, retry_after = charge(payload.project)
    if not allowed:
        raise RateLimited(retry_after)

    await session.execute(
        insert(Scope)
        .values(
            project=payload.project,
            source=payload.source,
            category=payload.category.value,
            page=payload.page,
            ruleset=payload.ruleset,
        )
        .on_conflict_do_nothing(
            index_elements=["project", "source", "category", "page", "ruleset"]
        )
    )
    scope = await session.scalar(
        select(Scope)
        .where(
            Scope.project == payload.project,
            Scope.source == payload.source,
            Scope.category == payload.category.value,
            Scope.page == payload.page,
            Scope.ruleset == payload.ruleset,
        )
        .with_for_update()
    )

    # A concurrent delivery of the same report may have committed while we waited.
    existing = await _find(session, payload.project, payload.report_id)
    if existing:
        replay = _replay(existing, digest)  # read before rollback expires the row
        await session.rollback()
        return replay

    result = ReportResult(
        report_id=payload.report_id,
        status=payload.status,
        outcome="not_applied",
        applied=False,
        submitted=len(payload.findings or []),
    )
    at = payload.scanned_at

    if payload.status != "complete":
        result.message = (
            f"{payload.status} report recorded; issue state unchanged. Only a complete "
            "report can resolve issues."
        )
    elif scope.last_scanned_at is not None and at <= scope.last_scanned_at:
        result.outcome = "stale"
        result.message = (
            "an equal or newer complete report was already applied for this scope; "
            "recorded, not applied"
        )
    else:
        await _apply(session, scope, payload, result)
        result.outcome = "applied"
        result.applied = True
        scope.last_scanned_at = at

    if result.outcome != "stale" and (
        scope.last_attempt_at is None or at >= scope.last_attempt_at
    ):
        scope.last_attempt_at = at
        scope.last_attempt_status = payload.status

    session.add(
        Report(
            report_id=payload.report_id,
            project=payload.project,
            scope_id=scope.id,
            scan_id=payload.scan_id,
            payload_digest=digest,
            status=payload.status,
            scanned_at=at,
            outcome=result.outcome,
            result=result.model_dump(exclude={"replayed"}),
        )
    )
    try:
        await session.commit()
    except IntegrityError:
        # Same report_id delivered concurrently through a different scope.
        await session.rollback()
        existing = await _find(session, payload.project, payload.report_id)
        if existing is None:
            raise
        return _replay(existing, digest)
    return result


async def _apply(
    session: AsyncSession, scope: Scope, payload: ReportIn, result: ReportResult
) -> None:
    at = payload.scanned_at
    prior = {
        key: resolved_at
        for key, resolved_at in (
            await session.execute(
                select(Issue.issue_key, Issue.resolved_at).where(Issue.scope_id == scope.id)
            )
        ).all()
    }

    rows = {}
    for f in payload.findings or []:
        key = issue_key(
            payload.project, payload.source, payload.category.value,
            payload.page, payload.ruleset, f.rule_id, f.locator,
        )
        rows[key] = {
            "issue_key": key,
            "scope_id": scope.id,
            "project": payload.project,
            "source": payload.source,
            "category": payload.category.value,
            "page": payload.page,
            "rule_id": f.rule_id,
            "locator": f.locator,
            "detail": f.detail,
            "severity": f.severity.value,
            "evidence": f.evidence,
            "help_url": f.help_url,
            "observation_count": 1,
            "first_seen_at": at,
            "last_seen_at": at,
            "resolved_at": None,
        }
        if key not in prior:
            result.new += 1
        elif prior[key] is not None:
            result.reopened += 1
        else:
            result.seen_again += 1

    if rows:
        stmt = insert(Issue).values(list(rows.values()))
        await session.execute(
            stmt.on_conflict_do_update(
                index_elements=[Issue.issue_key],
                set_={
                    "observation_count": Issue.__table__.c.observation_count + 1,
                    "last_seen_at": stmt.excluded.last_seen_at,
                    # detail, severity and evidence describe the issue; they are not its
                    # identity, so rewording or rescoring updates the row it already owns.
                    "detail": stmt.excluded.detail,
                    "severity": stmt.excluded.severity,
                    "evidence": stmt.excluded.evidence,
                    "help_url": stmt.excluded.help_url,
                    "resolved_at": None,
                },
            )
        )

    gone = [k for k, resolved_at in prior.items() if resolved_at is None and k not in rows]
    if gone:
        await session.execute(
            update(Issue).where(Issue.issue_key.in_(gone)).values(resolved_at=at)
        )
    result.resolved = len(gone)
