"""Minimal versioned migrations: numbered .sql files applied once, in order.

Chosen over Alembic to avoid a new dependency for a two-table-family schema; the cost is
no autogeneration and forward-only migrations. Each file runs in its own transaction and
is recorded in schema_migrations, so a partial failure leaves the previous state intact.
A Postgres advisory lock keeps two starting processes from applying the same file twice.
"""

from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"
_LOCK_ID = 74_110_001


async def migrate(engine: AsyncEngine) -> list[str]:
    """Apply pending migrations; returns the names applied by this call."""
    applied_now: list[str] = []
    async with engine.connect() as conn:
        await conn.execute(text("SELECT pg_advisory_lock(:id)"), {"id": _LOCK_ID})
        try:
            await conn.execute(
                text(
                    "CREATE TABLE IF NOT EXISTS schema_migrations ("
                    "name TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())"
                )
            )
            await conn.commit()
            done = {r[0] for r in await conn.execute(text("SELECT name FROM schema_migrations"))}
            for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
                if path.name in done:
                    continue
                # asyncpg cannot run multiple statements in one prepared call; use the
                # raw driver connection's simple-query protocol.
                raw = await conn.get_raw_connection()
                await raw.driver_connection.execute(path.read_text())
                await conn.execute(
                    text("INSERT INTO schema_migrations (name) VALUES (:n)"), {"n": path.name}
                )
                await conn.commit()
                applied_now.append(path.name)
        finally:
            await conn.execute(text("SELECT pg_advisory_unlock(:id)"), {"id": _LOCK_ID})
            await conn.commit()
    return applied_now
