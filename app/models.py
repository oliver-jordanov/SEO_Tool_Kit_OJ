from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, LargeBinary, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160), unique=True)
    domain: Mapped[str] = mapped_column(String(255))
    location_code: Mapped[int] = mapped_column(default=2276)
    language_code: Mapped[str] = mapped_column(String(16), default="de")
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ProjectCompetitor(Base):
    __tablename__ = "project_competitors"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    domain: Mapped[str] = mapped_column(String(255))


class ResearchRun(Base):
    __tablename__ = "research_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"), nullable=True)
    function: Mapped[str] = mapped_column(String(80), index=True)
    status: Mapped[str] = mapped_column(String(32), default="created", index=True)
    source: Mapped[str] = mapped_column(String(32), default="api")
    parameters_json: Mapped[str] = mapped_column(Text)
    cache_key: Mapped[str] = mapped_column(String(64), index=True)
    cache_hit: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ApiRequest(Base):
    __tablename__ = "api_requests"
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("research_runs.id", ondelete="CASCADE"))
    endpoint: Mapped[str] = mapped_column(String(255))
    request_hash: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32))
    task_id: Mapped[str | None] = mapped_column(String(100), nullable=True, unique=True)
    estimated_cost_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=0)
    actual_cost_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=0)
    status_code: Mapped[int | None] = mapped_column(nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ApiResponseBlob(Base):
    __tablename__ = "api_response_blobs"
    id: Mapped[int] = mapped_column(primary_key=True)
    api_request_id: Mapped[int] = mapped_column(ForeignKey("api_requests.id", ondelete="CASCADE"), unique=True)
    body_gzip: Mapped[bytes] = mapped_column(LargeBinary)
    schema_version: Mapped[str] = mapped_column(String(32), default="v3")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CacheEntry(Base):
    __tablename__ = "cache_entries"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("research_runs.id", ondelete="CASCADE"))
    response_blob_id: Mapped[int] = mapped_column(ForeignKey("api_response_blobs.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int | None] = mapped_column(ForeignKey("research_runs.id"), nullable=True)
    kind: Mapped[str] = mapped_column(String(80))
    state: Mapped[str] = mapped_column(String(32), default="queued", index=True)
    external_task_id: Mapped[str | None] = mapped_column(String(100), nullable=True, unique=True)
    payload_json: Mapped[str] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CostLedger(Base):
    __tablename__ = "cost_ledger"
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("research_runs.id", ondelete="CASCADE"))
    api_request_id: Mapped[int] = mapped_column(ForeignKey("api_requests.id", ondelete="CASCADE"))
    task_id: Mapped[str | None] = mapped_column(String(100), nullable=True, unique=True)
    function: Mapped[str] = mapped_column(String(80), index=True)
    estimated_cost_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=0)
    actual_cost_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=0)
    pricing_version: Mapped[str] = mapped_column(String(32), default="2026-08-07")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class SerpOrganicResult(Base):
    __tablename__ = "serp_organic_results"
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("research_runs.id", ondelete="CASCADE"), index=True)
    organic_position: Mapped[int] = mapped_column(Integer)
    serp_position: Mapped[int] = mapped_column(Integer)
    domain: Mapped[str] = mapped_column(String(255), default="")
    url: Mapped[str] = mapped_column(Text, default="")
    title: Mapped[str] = mapped_column(Text, default="")
    snippet: Mapped[str] = mapped_column(Text, default="")
    breadcrumb: Mapped[str] = mapped_column(Text, default="")
    is_own_domain: Mapped[bool] = mapped_column(Boolean, default=False)


class SerpFeature(Base):
    __tablename__ = "serp_features"
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("research_runs.id", ondelete="CASCADE"), index=True)
    feature: Mapped[str] = mapped_column(String(80))


class BacklinkSummary(Base):
    __tablename__ = "backlink_summaries"
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("research_runs.id", ondelete="CASCADE"), unique=True, index=True)
    data_json: Mapped[str] = mapped_column(Text)


class BacklinkReferringDomain(Base):
    __tablename__ = "backlink_referring_domains"
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("research_runs.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    data_json: Mapped[str] = mapped_column(Text)


class BacklinkItem(Base):
    __tablename__ = "backlink_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("research_runs.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    data_json: Mapped[str] = mapped_column(Text)


Index("ix_runs_function_created", ResearchRun.function, ResearchRun.created_at)
