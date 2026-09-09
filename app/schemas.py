from datetime import datetime
from enum import Enum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .config import settings


class Kind(str, Enum):
    """Closed set. An unrecognised kind is a scanner bug or a caller we did not expect,
    and either way it should fail loudly at the edge rather than land in the table and
    quietly break every GROUP BY downstream."""

    css = "css"
    ada = "ada"
    seo = "seo"


class Severity(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"


ProjectName = Annotated[
    str,
    Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._-]+$"),
]


class FindingIn(BaseModel):
    # extra="forbid" so a scanner that starts sending a field we do not store gets told,
    # instead of us silently dropping data someone believes is being recorded.
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    locator: str = Field(min_length=1, max_length=500)
    detail: str = Field(min_length=1, max_length=1000)
    severity: Severity = Severity.low


class AuditIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    project: ProjectName
    kind: Kind
    page: str = Field(min_length=1, max_length=500)
    findings: list[FindingIn] = Field(default_factory=list)

    @field_validator("findings")
    @classmethod
    def bounded(cls, value: list[FindingIn]) -> list[FindingIn]:
        # Reject rather than truncate: a half-recorded report would look like the page
        # got better, and the resolution pass would close findings that are still real.
        if len(value) > settings.max_findings_per_request:
            raise ValueError(
                f"at most {settings.max_findings_per_request} findings per request; "
                f"got {len(value)}. Split the report by page."
            )
        return value


class IngestResult(BaseModel):
    """Returned counts are the caller's proof that a retry did nothing. A client that
    posts the same report twice sees accepted=0 the second time and knows the first
    call landed, even if it never saw the response."""

    project: str
    kind: Kind
    page: str
    submitted: int
    accepted: int
    duplicates: int
    resolved: int


class FindingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    kind: Kind
    page: str
    locator: str
    detail: str
    severity: Severity
    seen_count: int
    first_seen: datetime
    last_seen: datetime


class SeverityCounts(BaseModel):
    high: int = 0
    medium: int = 0
    low: int = 0


class ProjectReport(BaseModel):
    project: str
    counts: SeverityCounts
    last_run: datetime | None = None
    findings: list[FindingOut]
