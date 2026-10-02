from sqlalchemy import text

from app import db
from app.migrate import migrate
from app.models import Base


async def test_migrations_are_idempotent_and_match_the_models():
    assert await migrate(db.engine) == []  # conftest already applied everything
    async with db.engine.connect() as conn:
        for table in Base.metadata.sorted_tables:
            cols = {r[0] for r in await conn.execute(text(
                "SELECT column_name FROM information_schema.columns WHERE table_name = :t"
            ), {"t": table.name})}
            assert cols == {c.name for c in table.columns}, table.name


async def test_upgrade_from_v1_only_database_keeps_legacy_rows():
    async with db.engine.begin() as conn:
        await conn.execute(text("INSERT INTO findings (dedupe_key, project, kind, page, locator, detail, severity, seen_count)"
                                " VALUES ('k', 'legacy', 'ada', '/', '#x', 'd', 'low', 1)"))
        for t in ("issues", "reports", "scopes"):
            await conn.execute(text(f"DROP TABLE {t}"))
        await conn.execute(text("DELETE FROM schema_migrations WHERE name = '0002_reports_v2.sql'"))
    assert await migrate(db.engine) == ["0002_reports_v2.sql"]
    async with db.engine.connect() as conn:
        assert (await conn.execute(text("SELECT count(*) FROM findings WHERE project='legacy'"))).scalar() == 1
