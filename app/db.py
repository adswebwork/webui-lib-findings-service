from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from .config import settings
from .models import Base

engine = create_async_engine(
    settings.database_url,
    # Modest pool: this fronts a handful of scanners, not a public API. Sized small on
    # purpose so a runaway client exhausts its own budget rather than the database's
    # connection slots.
    pool_size=5,
    max_overflow=5,
    pool_pre_ping=True,
)

SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session


async def create_all() -> None:
    """Schema creation for local development and tests.

    Real deployments get a migration tool; create_all cannot express the column changes
    and backfills a live table needs. It is here so `docker compose up` and pytest work
    without a migration step, not as a deployment path.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
