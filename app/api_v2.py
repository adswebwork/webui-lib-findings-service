import logging
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .db import get_session
from .ingest_v2 import RateLimited, ReportConflict, ingest_report
from .models import Issue, Scope
from .ratelimit import limiter
from .schemas_v2 import (
    IssuePage,
    IssueRow,
    ProjectDetail,
    ProjectSummary,
    ReportIn,
    ReportResult,
    ScopeOut,
)

log = logging.getLogger("findings")
router = APIRouter(prefix="/v2", tags=["v2"])

SEVERITIES = ("high", "medium", "low")
_rank = case({"high": 0, "medium": 1, "low": 2}, value=Issue.severity)


@router.post("/reports", response_model=ReportResult)
async def post_report(payload: ReportIn, session: AsyncSession = Depends(get_session)):
    """Submit one report for one (project, source, category, page, ruleset) scope.

    Safe to retry with the same report_id and body: the stored result is returned with
    replayed=true and nothing is written. The same report_id with a different body is a
    409. A complete report resolves issues absent from it; partial, failed and stale
    reports are recorded but never change issue state.
    """
    try:
        result = await ingest_report(session, payload, limiter.check)
    except ReportConflict:
        return JSONResponse(
            status_code=409,
            content={"detail": f"report_id {payload.report_id!r} was already used with different content"},
        )
    except RateLimited as e:
        return JSONResponse(
            status_code=429,
            headers={"Retry-After": str(e.retry_after)},
            content={"detail": "write budget exceeded for this project",
                     "retry_after_seconds": e.retry_after},
        )
    log.info(
        "report project=%s report_id=%s outcome=%s replayed=%s",
        payload.project, payload.report_id, result.outcome, result.replayed,
    )
    return result


def _health(open_total: int, scopes: int, failed: int, scanned: bool) -> str:
    if scopes == 0:
        return "no_scans"
    if failed:
        return "failed"
    if not scanned:
        return "no_scans"
    return "issues" if open_total else "clean"


async def _summaries(session: AsyncSession, project: str | None = None) -> list[ProjectSummary]:
    sq = select(
        Scope.project,
        func.count().label("scopes"),
        func.count().filter(Scope.last_attempt_status.in_(("failed", "partial"))).label("failed"),
        func.max(Scope.last_scanned_at).label("scanned"),
    ).group_by(Scope.project)
    iq = (
        select(Issue.project, Issue.severity, func.count())
        .where(Issue.resolved_at.is_(None))
        .group_by(Issue.project, Issue.severity)
    )
    if project:
        sq, iq = sq.where(Scope.project == project), iq.where(Issue.project == project)
    open_by: dict[str, dict[str, int]] = {}
    for p, sev, n in (await session.execute(iq)).all():
        open_by.setdefault(p, dict.fromkeys(SEVERITIES, 0))[sev] = n
    out = []
    for p, scopes, failed, scanned in (await session.execute(sq.order_by(Scope.project))).all():
        counts = open_by.get(p, dict.fromkeys(SEVERITIES, 0))
        out.append(ProjectSummary(
            project=p, open=counts, scopes=scopes, failed_scopes=failed,
            last_scanned_at=scanned,
            health=_health(sum(counts.values()), scopes, failed, scanned is not None),
        ))
    return out


@router.get("/projects", response_model=list[ProjectSummary])
async def list_projects(session: AsyncSession = Depends(get_session)):
    return await _summaries(session)


@router.get("/projects/{project}", response_model=ProjectDetail)
async def get_project(project: str, session: AsyncSession = Depends(get_session)):
    found = await _summaries(session, project)
    if not found:
        raise HTTPException(404, "no reports received for this project")
    scopes = (
        await session.scalars(
            select(Scope).where(Scope.project == project)
            .order_by(Scope.page, Scope.source, Scope.category, Scope.id)
        )
    ).all()
    return ProjectDetail(**found[0].model_dump(),
                         scope_list=[ScopeOut.model_validate(s, from_attributes=True) for s in scopes])


@router.get("/projects/{project}/issues", response_model=IssuePage)
async def list_issues(
    project: str,
    state: Literal["open", "resolved", "all"] = "open",
    severity: Literal["high", "medium", "low"] | None = None,
    category: str | None = None,
    source: str | None = None,
    page: str | None = None,
    rule_id: str | None = None,
    sort: Literal["severity", "last_seen", "first_seen", "page"] = "severity",
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
):
    filters = [Issue.project == project]
    if state == "open":
        filters.append(Issue.resolved_at.is_(None))
    elif state == "resolved":
        filters.append(Issue.resolved_at.is_not(None))
    for col, val in ((Issue.category, category), (Issue.source, source),
                     (Issue.page, page), (Issue.rule_id, rule_id)):
        if val:
            filters.append(col == val)

    # Counts ignore the severity filter so the filter chips can show what is available,
    # but cover the whole filtered set rather than the current page.
    counts = dict.fromkeys(SEVERITIES, 0)
    for sev, n in (await session.execute(
        select(Issue.severity, func.count()).where(*filters).group_by(Issue.severity)
    )).all():
        counts[sev] = n
    if severity:
        filters.append(Issue.severity == severity)
    total = counts[severity] if severity else sum(counts.values())

    order = {
        "severity": (_rank, Issue.last_seen_at.desc()),
        "last_seen": (Issue.last_seen_at.desc(),),
        "first_seen": (Issue.first_seen_at.desc(),),
        "page": (Issue.page, _rank),
    }[sort]
    rows = (await session.scalars(
        select(Issue).where(*filters).order_by(*order, Issue.id)  # id: stable tie-breaker
        .limit(limit).offset(offset)
    )).all()
    return IssuePage(total=total, limit=limit, offset=offset, counts=counts,
                     items=[_row(i) for i in rows])


def _row(i: Issue) -> IssueRow:
    data = {c: getattr(i, c) for c in IssueRow.model_fields if c != "state"}
    return IssueRow(**data, state="resolved" if i.resolved_at else "open")


@router.get("/issues/{issue_id}", response_model=IssueRow)
async def get_issue(issue_id: int, session: AsyncSession = Depends(get_session)):
    issue = await session.get(Issue, issue_id)
    if issue is None:
        raise HTTPException(404, "issue not found")
    return _row(issue)
