from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, allow_inf_nan=False)


class ProjectInput(Input):
    name: str = Field(min_length=2, max_length=80, pattern=r"^[\w .-]+$")
    slug: str = Field(min_length=2, max_length=64, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    environment: Literal["development", "staging", "production"] = "development"


class RuleInput(Input):
    name: str = Field(min_length=2, max_length=100)
    metric: Literal["error_rate", "p95_latency_ms"]
    threshold: float = Field(ge=0, le=3_600_000)
    min_samples: int = Field(ge=1, le=10000, default=10)
    window_minutes: int = Field(ge=1, le=1440, default=15)
    cooldown_minutes: int = Field(ge=1, le=1440, default=30)
    severity: Literal["critical", "high", "medium", "low"] = "high"
    detector: Literal["threshold", "ewma", "robust_mad"] = "threshold"
    sensitivity: float = Field(ge=1, le=20, default=3.0)
    ewma_alpha: float = Field(gt=0, le=1, default=0.3)


class RuleToggle(Input):
    enabled: bool


class RulePatch(Input):
    name: str | None = Field(default=None, min_length=2, max_length=100)
    metric: Literal["error_rate", "p95_latency_ms"] | None = None
    threshold: float | None = Field(default=None, ge=0, le=3_600_000)
    min_samples: int | None = Field(default=None, ge=1, le=10000)
    window_minutes: int | None = Field(default=None, ge=1, le=1440)
    cooldown_minutes: int | None = Field(default=None, ge=1, le=1440)
    severity: Literal["critical", "high", "medium", "low"] | None = None
    detector: Literal["threshold", "ewma", "robust_mad"] | None = None
    sensitivity: float | None = Field(default=None, ge=1, le=20)
    ewma_alpha: float | None = Field(default=None, gt=0, le=1)
    enabled: bool | None = None


class SLOInput(Input):
    name: str = Field(min_length=2, max_length=100)
    sli: Literal["success_rate", "latency"]
    objective: float = Field(gt=0, lt=100)
    latency_threshold_ms: float | None = Field(default=None, gt=0, le=3_600_000)
    window_minutes: int = Field(ge=5, le=10080, default=1440)
    short_window_minutes: int = Field(ge=1, le=1440, default=5)
    long_window_minutes: int = Field(ge=5, le=10080, default=60)
    min_samples: int = Field(ge=1, le=10000, default=20)


class SLOToggle(Input):
    enabled: bool


class ChangeEventInput(Input):
    kind: Literal["deployment", "configuration"]
    service: str = Field(min_length=1, max_length=128, pattern=r"^[\w .:/@-]+$")
    version: str = Field(min_length=1, max_length=100, pattern=r"^[\w .:/@-]+$")
    description: str = Field(min_length=2, max_length=300)
    recorded_at: datetime


class IncidentPatch(Input):
    status: Literal["ACKNOWLEDGED", "RESOLVED", "OPEN"]


class IncidentNoteInput(Input):
    content: str = Field(min_length=1, max_length=4000)


class CaseInput(Input):
    id: str = Field(min_length=1, max_length=64, pattern=r"^[\w.-]+$")
    expected: str = Field(max_length=256)
    baseline_output: str = Field(max_length=256)
    candidate_output: str = Field(max_length=256)
    input: str | None = Field(default=None, max_length=2000)
    baseline_latency_ms: float | None = Field(default=None, ge=0.0, le=60000.0)
    candidate_latency_ms: float | None = Field(default=None, ge=0.0, le=60000.0)
    baseline_tokens: int | None = Field(default=None, ge=0, le=1000000)
    candidate_tokens: int | None = Field(default=None, ge=0, le=1000000)


class DatasetInput(Input):
    name: str = Field(min_length=2, max_length=100)
    description: str | None = Field(default=None, max_length=300)
    cases: list[CaseInput] = Field(min_length=1, max_length=500)


class DatasetVersionInput(Input):
    description: str | None = Field(default=None, max_length=300)
    cases: list[CaseInput] = Field(min_length=1, max_length=500)


class EvaluationInput(Input):
    dataset_id: UUID
    baseline: str = Field(min_length=1, max_length=100)
    candidate: str = Field(min_length=1, max_length=100)
    grader: Literal["exact-match-v1", "json-validity-v1"] = "exact-match-v1"
    safety_patterns: list[Annotated[str, Field(min_length=1, max_length=256)]] | None = Field(
        default=None, max_length=50
    )
    latency_budget_ms: float | None = Field(default=None, ge=0.0, le=60000.0)
    cost_budget_tokens: int | None = Field(default=None, ge=0, le=1000000)
    repeats: Literal[1] = 1  # Regrading identical supplied outputs is not an independent repeat.
    mode: str = Field(default="offline-paired-replay", pattern=r"^(offline-paired-replay|sandboxed-execution)$")
    candidate_code: str | None = Field(default=None, max_length=50000)


class ProposalInput(Input):
    incident_id: UUID
    action: Literal["restart_service", "rollback_deployment"]
    target: str = Field(min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9_.:/-]+$")
    rollback_plan: str = Field(min_length=10, max_length=500)
    expires_minutes: int = Field(ge=5, le=120, default=30)


class ApprovalInput(Input):
    manifest_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


class RetentionInput(Input):
    retention_days: int = Field(ge=1, le=30)
