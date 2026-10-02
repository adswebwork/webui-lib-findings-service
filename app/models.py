from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Finding(Base):
    """One open or resolved problem, at one place, on one page, of one project.

    dedupe_key is the whole design. It is sha256(project|kind|page|locator), and the
    unique constraint on it is what makes ingest idempotent: the scanner runs on every
    page load, the client retries on network failure, and a developer hits 'audit'
    repeatedly while fixing things. Without the key, one problem becomes hundreds of
    rows within a day and the dashboard stops being readable.

    Note the key deliberately excludes `detail` and `severity`. Those are properties of
    the finding, not its identity -- if a rule's wording or scoring changes, that has to
    update the existing row rather than orphan it and create a new one.
    """

    __tablename__ = "findings"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    dedupe_key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)

    project: Mapped[str] = mapped_column(String(128), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    page: Mapped[str] = mapped_column(String(500), nullable=False)
    locator: Mapped[str] = mapped_column(String(500), nullable=False)

    detail: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False, default="low")

    seen_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    first_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Set when a later audit of the same (project, kind, page) no longer reports this
    # finding. Resolved rather than deleted, so "what did this page used to get wrong"
    # and a fix rate over time both stay answerable.
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        # The dashboard's only hot query: open findings for a project, worst first.
        Index(
            "ix_findings_project_open",
            "project",
            "resolved_at",
            "severity",
        ),
        # Closing out a run scans exactly this shape.
        Index("ix_findings_run_scope", "project", "kind", "page", "resolved_at"),
    )


class AuditRun(Base):
    """One row per audit submitted, so the dashboard can say when a project was last
    checked -- not only what was wrong the last time somebody looked."""

    __tablename__ = "audit_runs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    project: Mapped[str] = mapped_column(String(128), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    page: Mapped[str] = mapped_column(String(500), nullable=False)

    submitted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    accepted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duplicates: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    resolved: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index("ix_audit_runs_project_time", "project", "created_at"),
    )


# --- v2 -------------------------------------------------------------------------------
# The SQL files in migrations/ are the source of truth for the schema; these mappings are
# for queries. tests/test_migrations.py guards against drift.
from sqlalchemy import ForeignKey  # noqa: E402
from sqlalchemy.dialects.postgresql import JSONB  # noqa: E402


class Scope(Base):
    __tablename__ = "scopes"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    project: Mapped[str] = mapped_column(String(128), nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    page: Mapped[str] = mapped_column(String(500), nullable=False)
    ruleset: Mapped[str] = mapped_column(String(500), nullable=False)
    last_scanned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_attempt_status: Mapped[str | None] = mapped_column(String(16))


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    report_id: Mapped[str] = mapped_column(String(128), nullable=False)
    project: Mapped[str] = mapped_column(String(128), nullable=False)
    scope_id: Mapped[int] = mapped_column(ForeignKey("scopes.id"), nullable=False)
    scan_id: Mapped[str | None] = mapped_column(String(128))
    payload_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    scanned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    outcome: Mapped[str] = mapped_column(String(16), nullable=False)
    result: Mapped[dict] = mapped_column(JSONB, nullable=False)


class Issue(Base):
    __tablename__ = "issues"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    issue_key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    scope_id: Mapped[int] = mapped_column(ForeignKey("scopes.id"), nullable=False)
    project: Mapped[str] = mapped_column(String(128), nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    page: Mapped[str] = mapped_column(String(500), nullable=False)
    rule_id: Mapped[str] = mapped_column(String(128), nullable=False)
    locator: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    detail: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    evidence: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    help_url: Mapped[str | None] = mapped_column(String(500))
    observation_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
