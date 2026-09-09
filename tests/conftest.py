import os

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# Point the app at the test database before anything imports settings.
os.environ.setdefault(
    "FINDINGS_DATABASE_URL",
    "postgresql+asyncpg://genesis:genesis@localhost:55432/findings_test",
)

from app import db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Base  # noqa: E402
from app.ratelimit import limiter  # noqa: E402


@pytest_asyncio.fixture(autouse=True)
async def prepare():
    """Fresh schema state and a fresh connection pool for every test.

    An asyncpg connection belongs to the event loop that opened it. pytest-asyncio gives
    each test its own loop, so a pool shared across tests hands the second test a
    connection bound to the first test's dead loop -- which surfaces as a RuntimeError
    from inside whatever happened to touch the database first, not as anything that
    points at the pool. Disposing per test keeps the lifetime of a connection inside the
    lifetime of the loop that created it.

    create_all is idempotent, so this is a truncate in the steady state rather than a
    schema rebuild.
    """
    async with db.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        for table in reversed(Base.metadata.sorted_tables):
            await conn.execute(table.delete())

    limiter.reset()
    yield
    await db.engine.dispose()


@pytest_asyncio.fixture
async def client():
    # ASGITransport does not run the lifespan handler, which is what we want here:
    # the fixture above already owns schema setup, and running lifespan would create
    # the tables from a different loop again.
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


def audit(project="demo", kind="ada", page="/checkout", findings=None):
    return {
        "project": project,
        "kind": kind,
        "page": page,
        "findings": findings if findings is not None else [],
    }


def finding(locator, detail="image has no alt attribute", severity="high"):
    return {"locator": locator, "detail": detail, "severity": severity}
