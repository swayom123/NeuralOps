from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def uid() -> str:
    return str(uuid4())


def now() -> datetime:
    return datetime.now(UTC)


class Organization(Base):
    __tablename__ = "organizations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(100))
    slug: Mapped[str] = mapped_column(String(64), unique=True)


class Membership(Base):
    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("organization_id", "subject"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"))
    subject: Mapped[str] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(100))
    role: Mapped[str] = mapped_column(String(24))
    project_ids: Mapped[list] = mapped_column(JSON, default=list)


class UserSession(Base):
    __tablename__ = "user_sessions"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    membership_id: Mapped[str] = mapped_column(ForeignKey("memberships.id"))
    csrf_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Project(Base):
    __tablename__ = "projects"
    __table_args__ = (UniqueConstraint("organization_id", "slug"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    slug: Mapped[str] = mapped_column(String(64))
    environment: Mapped[str] = mapped_column(String(16))
    retention_days: Mapped[int] = mapped_column(Integer, default=7, server_default="7")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Credential(Base):
    __tablename__ = "ingestion_credentials"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    verifier: Mapped[str] = mapped_column(String(64), unique=True)
    prefix: Mapped[str] = mapped_column(String(16))
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    rate_minute: Mapped[int] = mapped_column(BigInteger, default=0)
    rate_count: Mapped[int] = mapped_column(Integer, default=0)


class Span(Base):
    __tablename__ = "spans"
    __table_args__ = (
        UniqueConstraint("organization_id", "project_id", "trace_id", "span_id"),
        Index("ix_spans_scope_time", "organization_id", "project_id", "start_ns"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    organization_id: Mapped[str] = mapped_column(String(36))
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"))
    trace_id: Mapped[str] = mapped_column(String(32))
    span_id: Mapped[str] = mapped_column(String(16))
    parent_span_id: Mapped[str] = mapped_column(String(16))
    operation: Mapped[str] = mapped_column(String(128))
    service: Mapped[str] = mapped_column(String(128))
    start_ns: Mapped[int] = mapped_column(BigInteger)
    end_ns: Mapped[int] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String(12))
    attributes: Mapped[dict] = mapped_column(JSON)
    links: Mapped[list] = mapped_column(JSON, default=list)
    redacted_count: Mapped[int] = mapped_column(Integer, default=0)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Trace(Base):
    __tablename__ = "traces"
    __table_args__ = (
        UniqueConstraint("organization_id", "project_id", "trace_id"),
        Index("ix_traces_scope_time", "organization_id", "project_id", "start_ns"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    organization_id: Mapped[str] = mapped_column(String(36))
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"))
    trace_id: Mapped[str] = mapped_column(String(32))
    operation: Mapped[str] = mapped_column(String(128))
    service: Mapped[str] = mapped_column(String(128))
    start_ns: Mapped[int] = mapped_column(BigInteger)
    duration_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(16))
    span_count: Mapped[int] = mapped_column(Integer)
    tokens: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    issues: Mapped[list] = mapped_column(JSON)
    critical_path: Mapped[list] = mapped_column(JSON, default=list)
    critical_path_duration_ms: Mapped[float | None] = mapped_column(Float, nullable=True)


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (Index("ix_jobs_claim", "status", "available_at"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    organization_id: Mapped[str] = mapped_column(String(36))
    project_id: Mapped[str] = mapped_column(String(36))
    kind: Mapped[str] = mapped_column(String(32))
    resource_id: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default="QUEUED")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(64), nullable=True)


class Rule(Base):
    __tablename__ = "rules"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    organization_id: Mapped[str] = mapped_column(String(36))
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"))
    name: Mapped[str] = mapped_column(String(100))
    metric: Mapped[str] = mapped_column(String(24))
    threshold: Mapped[float] = mapped_column(Float)
    min_samples: Mapped[int] = mapped_column(Integer)
    window_minutes: Mapped[int] = mapped_column(Integer)
    cooldown_minutes: Mapped[int] = mapped_column(Integer)
    severity: Mapped[str] = mapped_column(String(12))
    detector: Mapped[str] = mapped_column(String(24), default="threshold")
    sensitivity: Mapped[float] = mapped_column(Float, default=3.0)
    ewma_alpha: Mapped[float] = mapped_column(Float, default=0.3)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    state: Mapped[str] = mapped_column(String(24), default="insufficient_data")
    last_observed: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_fired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Detection(Base):
    __tablename__ = "detections"
    __table_args__ = (
        UniqueConstraint("organization_id", "project_id", "dedup_key"),
        Index("ix_detections_scope_time", "organization_id", "project_id", "evaluated_at"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    organization_id: Mapped[str] = mapped_column(String(36))
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"))
    rule_id: Mapped[str] = mapped_column(ForeignKey("rules.id"))
    incident_id: Mapped[str | None] = mapped_column(ForeignKey("incidents.id"), nullable=True)
    dedup_key: Mapped[str] = mapped_column(String(128))
    detector: Mapped[str] = mapped_column(String(24))
    metric: Mapped[str] = mapped_column(String(24))
    state: Mapped[str] = mapped_column(String(24))
    observed: Mapped[float | None] = mapped_column(Float, nullable=True)
    baseline: Mapped[float | None] = mapped_column(Float, nullable=True)
    deviation: Mapped[float | None] = mapped_column(Float, nullable=True)
    anomaly_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    threshold: Mapped[float] = mapped_column(Float)
    sample_count: Mapped[int] = mapped_column(Integer)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    evidence: Mapped[list] = mapped_column(JSON)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Incident(Base):
    __tablename__ = "incidents"
    __table_args__ = (UniqueConstraint("organization_id", "project_id", "dedup_key"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    organization_id: Mapped[str] = mapped_column(String(36))
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"))
    rule_id: Mapped[str] = mapped_column(ForeignKey("rules.id"))
    dedup_key: Mapped[str] = mapped_column(String(100))
    title: Mapped[str] = mapped_column(String(180))
    severity: Mapped[str] = mapped_column(String(12))
    status: Mapped[str] = mapped_column(String(24), default="OPEN")
    observed: Mapped[float] = mapped_column(Float)
    threshold: Mapped[float] = mapped_column(Float)
    sample_count: Mapped[int] = mapped_column(Integer)
    evidence: Mapped[list] = mapped_column(JSON)
    timeline: Mapped[list] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Hypothesis(Base):
    __tablename__ = "hypotheses"
    __table_args__ = (UniqueConstraint("incident_id", "rank"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    organization_id: Mapped[str] = mapped_column(String(36))
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"))
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id"), index=True)
    rank: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(180))
    evidence_class: Mapped[str] = mapped_column(String(24))
    algorithm: Mapped[str] = mapped_column(String(64))
    summary: Mapped[str] = mapped_column(String(500))
    counterevidence: Mapped[str] = mapped_column(String(500))
    missing: Mapped[list] = mapped_column(JSON)
    coverage: Mapped[float | None] = mapped_column(Float, nullable=True)
    dependency_context: Mapped[list] = mapped_column(JSON, default=list)
    change_evidence: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class EvidenceLink(Base):
    __tablename__ = "evidence_links"
    __table_args__ = (UniqueConstraint("hypothesis_id", "trace_id", "span_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    organization_id: Mapped[str] = mapped_column(String(36))
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"))
    hypothesis_id: Mapped[str] = mapped_column(ForeignKey("hypotheses.id", ondelete="CASCADE"), index=True)
    trace_id: Mapped[str] = mapped_column(String(32))
    span_id: Mapped[str] = mapped_column(String(16))
    operation: Mapped[str] = mapped_column(String(128))
    kind: Mapped[str] = mapped_column(String(16), default="supporting")


class IncidentNote(Base):
    __tablename__ = "incident_notes"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    organization_id: Mapped[str] = mapped_column(String(36))
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"))
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id", ondelete="CASCADE"), index=True)
    author_name: Mapped[str] = mapped_column(String(100))
    author_subject: Mapped[str] = mapped_column(String(100))
    content: Mapped[str] = mapped_column(String(4000))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class SLO(Base):
    __tablename__ = "slos"
    __table_args__ = (UniqueConstraint("organization_id", "project_id", "name"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    organization_id: Mapped[str] = mapped_column(String(36))
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"))
    name: Mapped[str] = mapped_column(String(100))
    sli: Mapped[str] = mapped_column(String(24))
    objective: Mapped[float] = mapped_column(Float)
    latency_threshold_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    window_minutes: Mapped[int] = mapped_column(Integer)
    short_window_minutes: Mapped[int] = mapped_column(Integer)
    long_window_minutes: Mapped[int] = mapped_column(Integer)
    min_samples: Mapped[int] = mapped_column(Integer)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class SLOSnapshot(Base):
    __tablename__ = "slo_snapshots"
    __table_args__ = (
        UniqueConstraint("slo_id", "calculated_minute"),
        Index("ix_slo_snapshots_scope_time", "organization_id", "project_id", "calculated_at"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    organization_id: Mapped[str] = mapped_column(String(36))
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"))
    slo_id: Mapped[str] = mapped_column(ForeignKey("slos.id"))
    calculated_minute: Mapped[int] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String(24))
    eligible_count: Mapped[int] = mapped_column(Integer)
    good_count: Mapped[int] = mapped_column(Integer)
    compliance: Mapped[float | None] = mapped_column(Float, nullable=True)
    error_budget_remaining: Mapped[float | None] = mapped_column(Float, nullable=True)
    short_burn_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    long_burn_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ChangeEvent(Base):
    __tablename__ = "change_events"
    __table_args__ = (Index("ix_change_events_scope_time", "organization_id", "project_id", "recorded_at"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    organization_id: Mapped[str] = mapped_column(String(36))
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"))
    kind: Mapped[str] = mapped_column(String(24))
    service: Mapped[str] = mapped_column(String(128))
    version: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(String(300))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Dataset(Base):
    __tablename__ = "datasets"
    __table_args__ = (
        CheckConstraint(
            "(parent_id IS NULL AND version = 1) OR (parent_id IS NOT NULL AND version > 1)",
            name="ck_dataset_lineage_version",
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    organization_id: Mapped[str] = mapped_column(String(36))
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"))
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(String(300), nullable=True)
    parent_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    manifest_hash: Mapped[str] = mapped_column(String(64))
    cases: Mapped[list] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Evaluation(Base):
    __tablename__ = "evaluations"
    __table_args__ = (UniqueConstraint("organization_id", "project_id", "idempotency_key"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    organization_id: Mapped[str] = mapped_column(String(36))
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"))
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id"))
    idempotency_key: Mapped[str] = mapped_column(String(64))
    request_hash: Mapped[str] = mapped_column(String(64))
    baseline: Mapped[str] = mapped_column(String(100))
    candidate: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(16), default="QUEUED")
    decision: Mapped[str | None] = mapped_column(String(16), nullable=True)
    manifest: Mapped[dict] = mapped_column(JSON)
    results: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Remediation(Base):
    __tablename__ = "remediations"
    __table_args__ = (UniqueConstraint("organization_id", "project_id", "idempotency_key"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    organization_id: Mapped[str] = mapped_column(String(36))
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"))
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id"))
    proposer: Mapped[str] = mapped_column(String(255))
    idempotency_key: Mapped[str] = mapped_column(String(64))
    manifest_hash: Mapped[str] = mapped_column(String(64))
    manifest: Mapped[dict] = mapped_column(JSON)
    state: Mapped[str] = mapped_column(String(24), default="PROPOSED")
    approver: Mapped[str | None] = mapped_column(String(255), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    organization_id: Mapped[str] = mapped_column(String(36), index=True)
    project_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    actor: Mapped[str] = mapped_column(String(255))
    action: Mapped[str] = mapped_column(String(80))
    target: Mapped[str] = mapped_column(String(128))
    outcome: Mapped[str] = mapped_column(String(24))
    request_id: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class RateBucket(Base):
    __tablename__ = "rate_buckets"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    minute: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    count: Mapped[int] = mapped_column(Integer, default=1)


class RuleVersion(Base):
    __tablename__ = "rule_versions"
    __table_args__ = (UniqueConstraint("rule_id", "version"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    organization_id: Mapped[str] = mapped_column(String(36))
    project_id: Mapped[str] = mapped_column(String(36))
    rule_id: Mapped[str] = mapped_column(ForeignKey("rules.id"))
    version: Mapped[int] = mapped_column(Integer)
    manifest: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


# Composite references enforce canonical tenant scope even if a future writer omits an application check.
from sqlalchemy import ForeignKeyConstraint  # noqa: E402

Project.__table__.append_constraint(UniqueConstraint("organization_id", "id", name="uq_project_scope"))
for model in (
    Credential,
    Span,
    Trace,
    Job,
    Rule,
    Detection,
    Incident,
    Hypothesis,
    EvidenceLink,
    IncidentNote,
    SLO,
    SLOSnapshot,
    ChangeEvent,
    Dataset,
    Evaluation,
    Remediation,
    RuleVersion,
):
    model.__table__.append_constraint(
        ForeignKeyConstraint(
            ["organization_id", "project_id"],
            ["projects.organization_id", "projects.id"],
            name=f"fk_{model.__tablename__}_project_scope",
        )
    )
for model in (Rule, Incident, Hypothesis, SLO, Dataset):
    model.__table__.append_constraint(
        UniqueConstraint("organization_id", "project_id", "id", name=f"uq_{model.__tablename__}_scope")
    )
for model, field, target in (
    (Incident, "rule_id", "rules"),
    (Detection, "rule_id", "rules"),
    (Detection, "incident_id", "incidents"),
    (Hypothesis, "incident_id", "incidents"),
    (EvidenceLink, "hypothesis_id", "hypotheses"),
    (IncidentNote, "incident_id", "incidents"),
    (SLOSnapshot, "slo_id", "slos"),
    (Dataset, "parent_id", "datasets"),
    (Evaluation, "dataset_id", "datasets"),
    (Remediation, "incident_id", "incidents"),
    (RuleVersion, "rule_id", "rules"),
):
    model.__table__.append_constraint(
        ForeignKeyConstraint(
            ["organization_id", "project_id", field],
            [f"{target}.organization_id", f"{target}.project_id", f"{target}.id"],
            name=f"fk_{model.__tablename__}_{target}_scope",
        )
    )

Index(
    "uq_dataset_lineage_version",
    Dataset.organization_id, Dataset.project_id,
    func.coalesce(Dataset.parent_id, Dataset.id), Dataset.version,
    unique=True,
)

AuditEvent.__table__.append_constraint(
    ForeignKeyConstraint(
        ["organization_id", "project_id"],
        ["projects.organization_id", "projects.id"],
        name="fk_audit_events_project_scope",
    )
)


class ExpiredTrace(Base):
    __tablename__ = "expired_traces"
    __table_args__ = (
        UniqueConstraint("organization_id", "project_id", "trace_id"),
        ForeignKeyConstraint(["organization_id", "project_id"], ["projects.organization_id", "projects.id"]),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    organization_id: Mapped[str] = mapped_column(String(36))
    project_id: Mapped[str] = mapped_column(String(36))
    trace_id: Mapped[str] = mapped_column(String(32))
    expired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
