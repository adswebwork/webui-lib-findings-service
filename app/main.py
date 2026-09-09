import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.responses import JSONResponse
from starlette.datastructures import Headers, MutableHeaders
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from .db import create_all, engine, get_session
from .ingest import ingest
from .models import AuditRun, Finding
from .ratelimit import limiter
from .schemas import (
    AuditIn,
    FindingOut,
    IngestResult,
    ProjectReport,
    SeverityCounts,
)

logging.basicConfig(
    level=logging.INFO,
    format='{"ts":"%(asctime)s","level":"%(levelname)s","msg":"%(message)s"}',
)
log = logging.getLogger("findings")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_all()
    yield
    await engine.dispose()


app = FastAPI(
    title="Genesis findings service",
    version="0.1.0",
    summary="Idempotent ingestion for scanner findings.",
    lifespan=lifespan,
)


class RequestContext:
    """A request id on every response and every log line for it.

    Ingest is retried by clients, so the same logical report arrives more than once.
    Without a correlation id, telling a retry apart from a genuinely new report in the
    logs means guessing from timestamps.

    Written as a plain ASGI middleware rather than with @app.middleware("http").
    BaseHTTPMiddleware runs the rest of the stack in a separate task, which breaks
    streaming responses and background tasks and rewrites any error raised downstream
    into a traceback that points at the middleware instead of the cause.
    """

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = Headers(scope=scope).get("x-request-id") or uuid.uuid4().hex
        started = time.perf_counter()
        status = 500

        async def send_with_context(message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                MutableHeaders(scope=message).append("x-request-id", request_id)
            await send(message)

        try:
            await self.app(scope, receive, send_with_context)
        finally:
            log.info(
                "%s %s -> %d in %.1fms rid=%s",
                scope.get("method", "-"),
                scope.get("path", "-"),
                status,
                (time.perf_counter() - started) * 1000,
                request_id,
            )


app.add_middleware(RequestContext)


@app.post("/v1/findings", response_model=IngestResult)
async def post_findings(
    payload: AuditIn,
    session: AsyncSession = Depends(get_session),
) -> IngestResult | JSONResponse:
    """Ingest one audit run. Safe to retry: the response tells you what a retry did.

    Backpressure is per project and returns 429 with Retry-After rather than dropping
    the report, because a dropped report is indistinguishable to the caller from a page
    that got better -- and the resolution pass would then close findings that are still
    real.
    """
    allowed, retry_after = limiter.check(payload.project)
    if not allowed:
        log.warning("rate limited project=%s", payload.project)
        return JSONResponse(
            status_code=429,
            headers={"Retry-After": str(retry_after)},
            content={
                "detail": "write budget exceeded for this project",
                "retry_after_seconds": retry_after,
            },
        )

    result = await ingest(session, payload)
    log.info(
        "ingest project=%s kind=%s page=%s submitted=%d accepted=%d duplicates=%d resolved=%d",
        result.project,
        result.kind.value,
        result.page,
        result.submitted,
        result.accepted,
        result.duplicates,
        result.resolved,
    )
    return result


@app.get("/v1/findings/{project}", response_model=ProjectReport)
async def get_findings(
    project: str,
    limit: int = 200,
    session: AsyncSession = Depends(get_session),
) -> ProjectReport:
    limit = max(1, min(limit, 1000))

    # Severity has to be ordered explicitly; alphabetically "high" sorts under "low".
    severity_rank = func.array_position(
        text("ARRAY['high','medium','low']"), Finding.severity
    )

    rows = await session.execute(
        select(Finding)
        .where(Finding.project == project, Finding.resolved_at.is_(None))
        .order_by(severity_rank, Finding.last_seen.desc())
        .limit(limit)
    )
    findings = list(rows.scalars().all())

    counts = SeverityCounts()
    tally = await session.execute(
        select(Finding.severity, func.count())
        .where(Finding.project == project, Finding.resolved_at.is_(None))
        .group_by(Finding.severity)
    )
    for severity, n in tally.all():
        setattr(counts, severity, n)

    last_run = await session.scalar(
        select(func.max(AuditRun.created_at)).where(AuditRun.project == project)
    )

    return ProjectReport(
        project=project,
        counts=counts,
        last_run=last_run,
        findings=[FindingOut.model_validate(f) for f in findings],
    )


@app.get("/healthz")
async def healthz(session: AsyncSession = Depends(get_session)) -> dict:
    """Liveness plus a real dependency check.

    A health check that only proves the process is running will keep a pod in the load
    balancer while every request 500s on a dead connection pool.
    """
    try:
        await session.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001 - the reason is the useful part here
        return JSONResponse(
            status_code=503, content={"status": "degraded", "database": str(exc)}
        )
    return {"status": "ok", "database": "ok"}
