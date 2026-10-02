"""v2 contract. See docs/DECISIONS.md for why identity, ordering and completeness look
the way they do."""

import hashlib
import json
from datetime import datetime, timezone
from typing import Annotated, Literal
from urllib.parse import urlsplit, urlunsplit

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from .config import settings
from .schemas import Kind, ProjectName, Severity

Token = Annotated[str, Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")]
SourceName = Annotated[str, Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9._/-]+$")]
ScanStatus = Literal["complete", "partial", "failed"]


def canonical_page(page: str) -> str:
    """Fragment dropped, scheme and host lowercased. Path and query are kept verbatim:
    /a?x=1 and /a?x=2 may be different pages, and merging them would let one page's scan
    resolve the other's issues. Bare paths (/checkout) pass through unchanged."""
    parts = urlsplit(page)
    if parts.scheme or parts.netloc:
        return urlunsplit(
            (parts.scheme.lower(), parts.netloc.lower(), parts.path, parts.query, "")
        )
    return urlunsplit(("", "", parts.path, parts.query, ""))


def issue_key(
    project: str, source: str, category: str, page: str, ruleset: str, rule_id: str,
    locator: str,
) -> str:
    """sha256 over a JSON array: length-delimited by construction, so no field value can
    be crafted to collide with another split of the same characters. The ruleset is part
    of identity so an issue always belongs to exactly one scope; changing the ruleset
    starts a new set of issues rather than letting two scopes fight over one row."""
    blob = json.dumps(
        [project, source, category, page, ruleset, rule_id, locator],
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


class FindingV2(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    rule_id: str = Field(min_length=1, max_length=128)  # what is wrong
    locator: str = Field(default="", max_length=500)  # where; "" = page-level
    detail: str = Field(min_length=1, max_length=1000)
    severity: Severity
    evidence: dict = Field(default_factory=dict)
    help_url: str | None = Field(default=None, max_length=500)


class ReportIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    report_id: Token  # generated once by the producer; reused on every retry
    scan_id: Token | None = None  # optional grouping of per-page reports
    project: ProjectName
    source: SourceName
    category: Kind
    page: str = Field(min_length=1, max_length=500)
    # What the producer checked. A scope is only authoritative for its own ruleset, so
    # enabling or disabling rules cannot mark unchecked issues as fixed.
    ruleset: str = Field(min_length=1, max_length=500)
    status: ScanStatus
    scanned_at: AwareDatetime  # when the check ran; the ordering key
    findings: list[FindingV2] | None = None

    @field_validator("page")
    @classmethod
    def _canon(cls, value: str) -> str:
        return canonical_page(value)

    @model_validator(mode="after")
    def _checks(self) -> "ReportIn":
        if self.status == "complete" and self.findings is None:
            raise ValueError("findings is required for a complete report (use [] for a clean scan)")
        items = self.findings or []
        if len(items) > settings.max_findings_per_request:
            raise ValueError(
                f"at most {settings.max_findings_per_request} findings per report; got "
                f"{len(items)}. Oversized reports are rejected, never truncated."
            )
        seen = set()
        for f in items:
            if (f.rule_id, f.locator) in seen:
                raise ValueError(f"duplicate finding {f.rule_id!r} at {f.locator!r}")
            seen.add((f.rule_id, f.locator))
        return self

    def digest(self) -> str:
        body = self.model_dump(mode="json")
        body["scanned_at"] = self.scanned_at.astimezone(timezone.utc).isoformat()
        body["findings"] = sorted(
            body["findings"] or [], key=lambda f: (f["rule_id"], f["locator"])
        )
        blob = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()


class ReportResult(BaseModel):
    report_id: str
    status: ScanStatus
    outcome: Literal["applied", "stale", "not_applied"]
    applied: bool
    replayed: bool = False
    submitted: int = 0
    new: int = 0
    seen_again: int = 0
    reopened: int = 0
    resolved: int = 0
    message: str | None = None


class IssueOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project: str
    source: str
    category: Kind
    page: str
    rule_id: str
    locator: str
    detail: str
    severity: Severity
    evidence: dict
    help_url: str | None
    observation_count: int
    first_seen_at: datetime
    last_seen_at: datetime
    resolved_at: datetime | None


class IssueRow(IssueOut):
    state: Literal["open", "resolved"]


class IssuePage(BaseModel):
    total: int
    limit: int
    offset: int
    counts: dict[str, int]  # severity totals over the whole filtered set
    items: list[IssueRow]


class ScopeOut(BaseModel):
    source: str
    category: Kind
    page: str
    ruleset: str
    last_scanned_at: datetime | None
    last_attempt_at: datetime | None
    last_attempt_status: ScanStatus | None


class ProjectSummary(BaseModel):
    project: str
    health: Literal["no_scans", "failed", "clean", "issues"]
    open: dict[str, int]
    last_scanned_at: datetime | None
    failed_scopes: int
    scopes: int


class ProjectDetail(ProjectSummary):
    scope_list: list[ScopeOut]
