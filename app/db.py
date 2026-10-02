from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from .config import settings
from .migrate import migrate

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
    """Bring the schema up to date by applying pending migrations (see app/migrate.py)."""
    await migrate(engine)
