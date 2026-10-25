"""OpenAPI response contracts. Frontend types are generated from these schemas."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Output(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Page[T](Output):
    items: list[T]
    next_cursor: str | None = None


class OrganizationView(Output):
    id: str
    name: str
    slug: str


class IdentityView(Output):
    id: str
    name: str
    role: Literal["admin", "viewer", "developer", "operator", "approver", "executor"]
    organization: OrganizationView
    development: bool
    remote_execution: bool


class ProjectView(Output):
    id: str
    name: str
    slug: str
    environment: str
    retention_days: int
    created_at: datetime


class CredentialView(Output):
    id: str
    project_id: str
    prefix: str
    revoked: bool
    expires_at: datetime
    created_at: datetime


class IssuedCredential(CredentialView):
    secret: str
    notice: str


class TraceView(Output):
    id: str
    trace_id: str
    operation: str
    service: str
    start_ns: int
    duration_ms: float | None
    status: str
    span_count: int
    tokens: int | None
    issues: list[str]
    critical_path: list[str]
    critical_path_duration_ms: float | None


class SpanLink(Output):
    trace_id: str
    span_id: str


class SpanView(Output):
    id: str
    span_id: str
    parent_span_id: str
    operation: str
    service: str
    start_ns: int
    end_ns: int
    status: str
    attributes: dict[str, str | int]
    links: list[SpanLink]
    redacted_count: int


class TraceDetailView(TraceView):
    spans: list[SpanView]
    truncated: bool
    privacy: str


class SeriesPoint(Output):
    at: str
    sample_count: int
    p50: float | None
    p95: float | None
    p99: float | None


class Failure(Output):
    category: str
    count: int


class SummaryView(Output):
    source: str
    calculated_at: datetime
    hours: int
    executions: int
    eligible_count: int
    success_rate: float | None
    p95_ms: float | None
    active_incidents: int
    tokens: int | None
    token_trace_coverage: int
    estimated_cost: float | None
    cost_reason: str
    percentile_method: str
    series: list[SeriesPoint]
    failures: list[Failure]
    jobs: dict[str, int]


class ServiceView(Output):
    name: str
    calls: int
    errors: int
    p95_ms: float | None
    status: str
    last_seen: datetime


class EdgeView(Output):
    source: str
    target: str
    provenance: str


class ServicesView(Page[ServiceView]):
    edges: list[EdgeView]


class RuleView(Output):
    id: str
    name: str
    metric: str
    threshold: float
    min_samples: int
    window_minutes: int
    cooldown_minutes: int
    severity: str
    detector: str
    sensitivity: float
    ewma_alpha: float
    enabled: bool
    version: int
    state: str
    last_observed: float | None


class RuleVersionView(Output):
    id: str
    rule_id: str
    version: int
    manifest: dict
    created_at: datetime


class DetectionView(Output):
    id: str
    rule_id: str
    incident_id: str | None
    detector: str
    metric: str
    state: str
    observed: float | None
    baseline: float | None
    deviation: float | None
    anomaly_score: float | None
    threshold: float
    sample_count: int
    window_start: datetime
    window_end: datetime
    evidence: list[str]
    evaluated_at: datetime


class RulePreviewView(Output):
    detector: str
    state: str
    observed: float | None
    baseline: float | None
    deviation: float | None
    anomaly_score: float | None
    sample_count: int
    would_fire: bool
    limitations: str


class TimelineEvent(Output):
    action: str
    actor: str
    at: str


class IncidentView(Output):
    id: str
    title: str
    severity: str
    status: str
    observed: float
    threshold: float
    sample_count: int
    evidence: list[str]
    timeline: list[TimelineEvent]
    created_at: datetime


class IncidentNoteView(Output):
    id: str
    incident_id: str
    author_name: str
    author_subject: str
    content: str
    created_at: datetime


class SupportingEvidence(Output):
    trace_id: str
    span_id: str
    operation: str


class ChangeEvidence(Output):
    id: str
    kind: str
    service: str
    version: str
    description: str
    recorded_at: datetime


class HypothesisView(Output):
    id: str
    rank: int
    title: str
    evidence_class: str
    summary: str
    supporting: list[SupportingEvidence]
    contradicting: list[SupportingEvidence]
    counterevidence: str
    missing: list[str]
    coverage: float | None
    dependency_context: list[str]
    change_evidence: list[ChangeEvidence]


class HypothesesView(Page[HypothesisView]):
    state: str
    limitations: str


class SLOSnapshotView(Output):
    id: str
    status: str
    eligible_count: int
    good_count: int
    compliance: float | None
    error_budget_remaining: float | None
    short_burn_rate: float | None
    long_burn_rate: float | None
    window_start: datetime
    window_end: datetime
    calculated_at: datetime


class SLOView(Output):
    id: str
    name: str
    sli: str
    objective: float
    latency_threshold_ms: float | None
    window_minutes: int
    short_window_minutes: int
    long_window_minutes: int
    min_samples: int
    enabled: bool
    created_at: datetime
    latest: SLOSnapshotView | None = None
    trend: list[SLOSnapshotView] = Field(default_factory=list)


class ChangeEventView(Output):
    id: str
    kind: str
    service: str
    version: str
    description: str
    recorded_at: datetime
    created_at: datetime


class DatasetView(Output):
    id: str
    name: str
    version: int
    manifest_hash: str
    case_count: int
    created_at: datetime
    parent_id: str | None = None
    description: str | None = None
    cases: list[dict[str, object]] | None = None


class CaseResult(Output):
    id: str
    baseline_pass: bool | None
    candidate_pass: bool | None
    baseline_task_pass: bool | None = None
    baseline_safety_pass: bool | None = None
    candidate_task_pass: bool | None = None
    candidate_safety_pass: bool | None = None
    baseline_latency_pass: bool | None = None
    candidate_latency_pass: bool | None = None
    baseline_token_pass: bool | None = None
    candidate_token_pass: bool | None = None
    safety_pass: bool | None = None
    task_pass: bool | None = None


class EvaluationResults(Output):
    sample_count: int | None = None
    baseline_score: float | None = None
    candidate_score: float | None = None
    safety_score: float | None = None
    interval_95: list[float] | None = None
    paired_delta: float | None = None
    repeats: int | None = None
    missing_measurements: bool | None = None
    measurement_source: str | None = None
    grader: str | None = None
    contamination: dict[str, object] | None = None
    sandbox_errors: list[str] | None = None
    method: str | None = None
    limitations: str | None = None
    cases: list[CaseResult] | None = None


class EvaluationView(Output):
    id: str
    baseline: str
    candidate: str
    dataset_id: str
    status: str
    decision: str | None
    created_at: datetime
    manifest: dict[str, object]
    results: EvaluationResults


class EvaluationReportView(Output):
    id: str
    organization_id: str
    project_id: str
    dataset_id: str
    dataset_version: int
    dataset_hash: str
    baseline: str
    candidate: str
    status: str
    decision: str | None
    created_at: datetime
    manifest: dict[str, object]
    results: EvaluationResults
    report_checksum: str


class RemediationView(Output):
    id: str
    incident_id: str
    manifest_hash: str
    manifest: dict[str, object]
    state: str
    proposer: str
    approver: str | None
    expires_at: datetime
    created_at: datetime
    execution_enabled: bool = False
    disabled_reason: str = "Remote executor unavailable."


class RemediationsView(Page[RemediationView]):
    execution_enabled: bool
    disabled_reason: str


class AuditView(Output):
    id: str
    project_id: str | None
    actor: str
    action: str
    target: str
    outcome: str
    request_id: str
    created_at: datetime


class ModelView(Output):
    model: str
    provider: str
    calls: int
    errors: int
    p95_ms: float | None
    input_tokens: int | None
    output_tokens: int | None


class ToolView(Output):
    name: str
    calls: int
    errors: int
    p95_ms: float | None


class AnalyticsView(Output):
    models: list[ModelView]
    tools: list[ToolView]
    input_tokens: int | None
    output_tokens: int | None
    usage_coverage: int
    span_count: int


class ErrorView(Output):
    code: str
    message: str
    request_id: str
