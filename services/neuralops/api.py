import ipaddress
import json
import secrets
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Annotated, Literal
from urllib.parse import urlparse
from uuid import UUID

from authlib.integrations.starlette_client import OAuth
from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import RedirectResponse, Response
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from starlette.concurrency import run_in_threadpool
from starlette.middleware.sessions import SessionMiddleware

from . import contracts as contract
from .config import settings
from .db import audit, ensure_runtime_role, ready
from .domain import detection_result, manifest_hash, percentile, queue_diagnosis, scope
from .http import configure
from .models import (
    SLO,
    AuditEvent,
    ChangeEvent,
    Credential,
    Dataset,
    Detection,
    Evaluation,
    EvidenceLink,
    ExpiredTrace,
    Hypothesis,
    Incident,
    IncidentNote,
    Job,
    Membership,
    Organization,
    Project,
    Remediation,
    Rule,
    RuleVersion,
    SLOSnapshot,
    Span,
    Trace,
    UserSession,
    now,
)
from .schemas import (
    ApprovalInput,
    ChangeEventInput,
    DatasetInput,
    DatasetVersionInput,
    EvaluationInput,
    IncidentNoteInput,
    IncidentPatch,
    ProjectInput,
    ProposalInput,
    RetentionInput,
    RuleInput,
    RulePatch,
    SLOInput,
    SLOToggle,
)
from .security import (
    DB,
    Actor,
    consume_rate,
    digest,
    fail,
    new_session,
    project_scope,
    require,
    scoped,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await run_in_threadpool(ensure_runtime_role, "neuralops_api")
    yield


app = FastAPI(
    lifespan=lifespan,
    title="NeuralOps Control API",
    responses={
        code: {"model": contract.ErrorView}
        for code in (400, 401, 403, 404, 409, 410, 413, 415, 422, 429, 503)
    },
    version="0.1.0",
    openapi_url="/v1/openapi.json" if settings().environment != "production" else None,
    docs_url="/v1/docs" if settings().environment != "production" else None,
)
configure(app)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings().session_secret,
    session_cookie="neuralops_oidc",
    https_only=settings().environment == "production",
    same_site="lax",
    max_age=600,
)
oauth = OAuth()
if settings().oidc_issuer:
    oauth.register(
        "identity",
        client_id=settings().oidc_client_id,
        client_secret=settings().oidc_client_secret,
        server_metadata_url=f"{settings().oidc_issuer.rstrip('/')}/.well-known/openid-configuration",
        client_kwargs={
            "scope": "openid profile email",
            "code_challenge_method": "S256",
        },
    )

ProjectId = Annotated[UUID, Query()]
PageLimit = Annotated[int, Query(ge=1, le=100)]


def serialize(obj, exclude: set[str] | None = None):
    hidden = {
        "organization_id",
        "verifier",
        "csrf_hash",
        "idempotency_key",
        "request_hash",
        "rate_count",
        "rate_minute",
    } | (exclude or set())
    return {c.name: getattr(obj, c.name) for c in obj.__table__.columns if c.name not in hidden}


def listing(db: DB, actor, model, project_id: str, limit=50, cursor: UUID | None = None):
    project_scope(db, actor, project_id)
    query = select(model).where(*scope(model, actor.organization_id, project_id))
    if hasattr(model, "deleted_at"):
        query = query.where(model.deleted_at.is_(None))
    if cursor:
        query = query.where(model.id < str(cursor))
    rows = list(db.scalars(query.order_by(model.id.desc()).limit(limit + 1)))
    return {
        "items": [serialize(r, {"cases"}) for r in rows[:limit]],
        "next_cursor": rows[limit - 1].id if len(rows) > limit else None,
    }


def idempotency(value: str | None):
    if not value or not 8 <= len(value) <= 64 or not all(c.isalnum() or c in "-_" for c in value):
        fail(422, "IDEMPOTENCY_REQUIRED", "Use an 8–64 character Idempotency-Key.")
    return value


def commit(db):
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        fail(
            409,
            "CONFLICT",
            "Resource already exists or a concurrent change occurred. Refresh and retry.",
        )


def flush(db):
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        fail(409, "CONFLICT", "Resource already exists or conflicts with tenant scope.")


@app.get("/health/live")
def live():
    return {"status": "alive"}


@app.get("/health/ready")
def readiness():
    ready()
    return {"status": "ready"}


@app.get("/v1/auth/config")
def auth_config():
    return {
        "development_auth": settings().dev_auth and settings().environment != "production",
        "oidc_enabled": bool(settings().oidc_issuer),
        "remote_execution": False,
    }


@app.post("/v1/auth/development")
def development_login(request: Request, db: DB, response: Response):
    config = settings()
    consume_rate("development-login", 10)
    origin_host = urlparse(config.public_origin).hostname
    client = request.client.host if request.client else ""
    local_client = client == "testclient"
    try:
        local_client = local_client or ipaddress.ip_address(client).is_private
    except ValueError:
        pass
    if (
        config.environment == "production"
        or not config.dev_auth
        or origin_host not in {"localhost", "127.0.0.1"}
        or not local_client
    ):
        fail(404, "NOT_FOUND", "Development sign-in unavailable.")
    if request.headers.get("origin") != config.public_origin:
        fail(403, "CSRF_REJECTED", "Request origin is invalid.")
    org = db.scalar(select(Organization).where(Organization.slug == "local"))
    if not org:
        org = Organization(name="Local workspace", slug="local")
        db.add(org)
        flush(db)
    member = db.scalar(
        select(Membership).where(
            Membership.organization_id == org.id,
            Membership.subject == "development-admin",
        )
    )
    if not member:
        member = Membership(
            organization_id=org.id,
            subject="development-admin",
            name="Local operator",
            role="admin",
        )
        db.add(member)
        flush(db)
    sessions = db.scalar(
        select(func.count())
        .select_from(UserSession)
        .where(UserSession.membership_id == member.id, UserSession.expires_at > now())
    )
    if sessions >= 20:
        fail(
            429,
            "RATE_LIMITED",
            "Too many active development sessions. Sign out or wait for expiry.",
        )
    new_session(db, member, response, request.state.request_id)
    commit(db)
    return {"status": "signed_in", "mode": "isolated_development"}


@app.get("/v1/auth/login")
async def login(request: Request):
    if not settings().oidc_issuer:
        fail(503, "IDENTITY_UNAVAILABLE", "OIDC provider is not configured.")
    consume_rate(f"oidc-login:{request.client.host}", 20)
    return await oauth.identity.authorize_redirect(
        request,
        f"{settings().public_origin}/api/v1/auth/callback",
        nonce=secrets.token_urlsafe(32),
    )


@app.get("/v1/auth/callback")
async def callback(request: Request, db: DB):
    if not settings().oidc_issuer:
        fail(503, "IDENTITY_UNAVAILABLE", "OIDC provider is not configured.")
    try:
        token = await oauth.identity.authorize_access_token(request)
        info = token.get("userinfo")
        # Authlib verifies ID-token signature, issuer, audience, nonce, expiry and state.
        if not info or info.get("iss") != settings().oidc_issuer or not info.get("sub"):
            fail(401, "INVALID_IDENTITY", "Identity validation failed.")
        member = db.scalar(select(Membership).where(Membership.subject == info["sub"]))
        if not member:
            fail(
                403,
                "NOT_PROVISIONED",
                "Ask an administrator to provision your membership.",
            )
        response = RedirectResponse("/app/local/select/overview", status_code=303)
        new_session(db, member, response, request.state.request_id)
        request.session.clear()
        commit(db)
        return response
    except HTTPException:
        request.session.clear()
        raise
    except Exception:  # noqa: BLE001 — security/process boundary; redact error details
        request.session.clear()
        fail(
            401,
            "IDENTITY_REJECTED",
            "Sign-in failed. Restart sign-in or contact your administrator.",
        )


@app.post("/v1/auth/logout")
def logout(request: Request, db: DB, actor: Actor, response: Response):
    session = db.get(UserSession, digest(request.cookies.get("neuralops_session", "")))
    db.delete(session)
    audit(
        db,
        actor.organization_id,
        actor.subject,
        "session.terminated",
        actor.id,
        request.state.request_id,
    )
    commit(db)
    response.delete_cookie("neuralops_session", path="/")
    response.delete_cookie("neuralops_csrf", path="/")
    return {"status": "signed_out"}


@app.get("/v1/me", response_model=contract.IdentityView)
def me(db: DB, actor: Actor):
    org = db.get(Organization, actor.organization_id)
    return {
        "id": actor.id,
        "name": actor.name,
        "role": actor.role,
        "organization": {"id": org.id, "name": org.name, "slug": org.slug},
        "development": actor.subject == "development-admin",
        "remote_execution": False,
    }


@app.get("/v1/projects", response_model=contract.Page[contract.ProjectView])
def projects(db: DB, actor: Actor):
    query = select(Project).where(Project.organization_id == actor.organization_id)
    if actor.role != "admin":
        query = query.where(Project.id.in_(actor.project_ids))
    return {"items": [serialize(p) for p in db.scalars(query.order_by(Project.created_at).limit(100))]}


@app.post("/v1/projects", status_code=201, response_model=contract.ProjectView)
def create_project(body: ProjectInput, request: Request, db: DB, actor: Actor):
    require(actor, "admin")
    if (
        db.scalar(
            select(func.count()).select_from(Project).where(Project.organization_id == actor.organization_id)
        )
        >= 100
    ):
        fail(429, "PROJECT_QUOTA", "Workspace project limit reached.")
    project = Project(organization_id=actor.organization_id, **body.model_dump())
    db.add(project)
    flush(db)
    audit(
        db,
        actor.organization_id,
        actor.subject,
        "project.created",
        project.id,
        request.state.request_id,
        project_id=project.id,
    )
    commit(db)
    return serialize(project)


@app.get("/v1/credentials", response_model=contract.Page[contract.CredentialView])
def credentials(project_id: ProjectId, db: DB, actor: Actor):
    require(actor, "admin")
    return listing(db, actor, Credential, str(project_id), 100)


@app.post("/v1/credentials", status_code=201, response_model=contract.IssuedCredential)
def create_credential(project_id: ProjectId, request: Request, db: DB, actor: Actor):
    require(actor, "admin")
    project_scope(db, actor, str(project_id))
    if (
        db.scalar(
            select(func.count())
            .select_from(Credential)
            .where(
                *scope(Credential, actor.organization_id, str(project_id)),
                Credential.revoked.is_(False),
            )
        )
        >= 10
    ):
        fail(
            429,
            "CREDENTIAL_QUOTA",  # pragma: allowlist secret — public error code, not a credential.
            "Revoke an existing credential before issuing another.",
        )
    secret = "nop_" + secrets.token_urlsafe(36)  # pragma: allowlist secret — runtime cryptographic generation, no literal secret.
    credential = Credential(
        organization_id=actor.organization_id,
        project_id=str(project_id),
        verifier=digest(secret),
        prefix=secret[:12],
        expires_at=now() + timedelta(days=30),
    )
    db.add(credential)
    flush(db)
    audit(
        db,
        actor.organization_id,
        actor.subject,
        "credential.created",
        credential.id,
        request.state.request_id,
        project_id=str(project_id),
    )
    commit(db)
    return {
        **serialize(credential),
        "secret": secret,
        "notice": "Shown once. Store securely; never embed in client bundles.",
    }


@app.delete("/v1/credentials/{identifier}")
def revoke_credential(identifier: UUID, project_id: ProjectId, request: Request, db: DB, actor: Actor):
    require(actor, "admin")
    credential = scoped(db, actor, Credential, str(identifier), str(project_id))
    credential.revoked = True
    audit(
        db,
        actor.organization_id,
        actor.subject,
        "credential.revoked",
        credential.id,
        request.state.request_id,
        project_id=str(project_id),
    )
    commit(db)
    return {"status": "revoked"}


def time_bounds(hours: int, from_time: datetime | None = None, to_time: datetime | None = None):
    end = to_time or now()
    start = from_time or end - timedelta(hours=hours)
    if (
        not end.tzinfo
        or not start.tzinfo
        or start >= end
        or end - start > timedelta(days=7)
        or end > now() + timedelta(minutes=5)
    ):
        fail(
            422,
            "INVALID_TIME_RANGE",
            "Use timezone-aware timestamps spanning at most 7 days.",
        )
    return int(start.timestamp() * 1e9), int(end.timestamp() * 1e9)


@app.get("/v1/traces", response_model=contract.Page[contract.TraceView])
def traces(
    project_id: ProjectId,
    db: DB,
    actor: Actor,
    hours: int = Query(24, ge=1, le=168),
    status: str | None = Query(None, pattern="^(ok|error|incomplete)$"),
    service: str | None = Query(None, max_length=128),
    search: str = Query("", max_length=128),
    limit: PageLimit = 50,
    cursor: UUID | None = None,
):
    project_scope(db, actor, str(project_id))
    start, end = time_bounds(hours)
    query = select(Trace).where(
        *scope(Trace, actor.organization_id, str(project_id)),
        Trace.start_ns.between(start, end),
    )
    if status:
        query = query.where(Trace.status == status)
    if service:
        query = query.where(Trace.service == service)
    if search:
        query = query.where(
            Trace.operation.icontains(search, autoescape=True)
            | Trace.trace_id.icontains(search, autoescape=True)
        )
    if cursor:
        query = query.where(Trace.id < str(cursor))
    rows = list(db.scalars(query.order_by(Trace.id.desc()).limit(limit + 1)))
    return {
        "items": [serialize(t) for t in rows[:limit]],
        "next_cursor": rows[limit - 1].id if len(rows) > limit else None,
        "sort": "id_desc",
        "source": "measured",
    }


@app.get("/v1/traces/{trace_id}", response_model=contract.TraceDetailView)
def trace_detail(trace_id: str, project_id: ProjectId, db: DB, actor: Actor):
    project_scope(db, actor, str(project_id))
    if len(trace_id) != 32:
        fail(404, "NOT_FOUND", "Trace not found.")
    trace = db.scalar(
        select(Trace).where(
            *scope(Trace, actor.organization_id, str(project_id)),
            Trace.trace_id == trace_id,
        )
    )
    if not trace:
        expired = db.scalar(
            select(ExpiredTrace).where(
                *scope(ExpiredTrace, actor.organization_id, str(project_id)),
                ExpiredTrace.trace_id == trace_id,
            )
        )
        if expired:
            fail(410, "EVIDENCE_EXPIRED", "Trace evidence expired under the project retention policy.")
        fail(404, "NOT_FOUND", "Trace not found or reconstruction pending.")
    spans = list(
        db.scalars(
            select(Span)
            .where(
                *scope(Span, actor.organization_id, str(project_id)),
                Span.trace_id == trace_id,
            )
            .order_by(Span.start_ns)
            .limit(2001)
        )
    )
    return {
        **serialize(trace),
        "spans": [serialize(s) for s in spans[:2000]],
        "truncated": len(spans) > 2000,
        "privacy": "Metadata only. Events, bodies, headers and non-allowlisted attributes are discarded before storage.",
    }


@app.get("/v1/metrics/summary", response_model=contract.SummaryView)
def metrics(project_id: ProjectId, db: DB, actor: Actor, hours: int = Query(24, ge=1, le=168)):
    project_scope(db, actor, str(project_id))
    start, end = time_bounds(hours)
    rows = list(
        db.scalars(
            select(Trace)
            .where(
                *scope(Trace, actor.organization_id, str(project_id)),
                Trace.start_ns.between(start, end),
            )
            .limit(10001)
        )
    )
    if len(rows) > 10000:
        fail(
            422,
            "WINDOW_TOO_LARGE",
            "Select a smaller time window; maximum 10,000 traces per aggregation.",
        )
    eligible = [t for t in rows if t.status != "incomplete"]
    durations = [t.duration_ms for t in eligible if t.duration_ms is not None]
    token_values = [t.tokens for t in rows if t.tokens is not None]
    active = db.scalar(
        select(func.count())
        .select_from(Incident)
        .where(
            *scope(Incident, actor.organization_id, str(project_id)),
            Incident.status != "RESOLVED",
        )
    )
    series = []
    for i in range(24):
        lower, upper = (
            start + (end - start) * i // 24,
            start + (end - start) * (i + 1) // 24,
        )
        bucket = [
            t.duration_ms for t in eligible if lower <= t.start_ns < upper and t.duration_ms is not None
        ]
        series.append(
            {
                "at": datetime.fromtimestamp(lower / 1e9, tz=now().tzinfo).isoformat(),
                "sample_count": len(bucket),
                "p50": percentile(bucket, 0.5),
                "p95": percentile(bucket, 0.95),
                "p99": percentile(bucket, 0.99),
            }
        )
    jobs = db.execute(
        select(Job.status, func.count())
        .where(*scope(Job, actor.organization_id, str(project_id)))
        .group_by(Job.status)
    ).all()
    return {
        "source": "measured",
        "calculated_at": now(),
        "hours": hours,
        "executions": len(rows),
        "eligible_count": len(eligible),
        "success_rate": sum(t.status == "ok" for t in eligible) / len(eligible) * 100 if eligible else None,
        "p95_ms": percentile(durations, 0.95),
        "active_incidents": active,
        "tokens": sum(token_values) if token_values else None,
        "token_trace_coverage": len(token_values),
        "estimated_cost": None,
        "cost_reason": "Pricing is not configured; no estimate is inferred.",
        "percentile_method": "nearest-rank",
        "series": series,
        "failures": [
            {
                "category": "Execution error",
                "count": sum(t.status == "error" for t in rows),
            },
            {
                "category": "Incomplete trace",
                "count": sum(t.status == "incomplete" for t in rows),
            },
        ],
        "jobs": dict(jobs),
    }


@app.get("/v1/services", response_model=contract.ServicesView)
def services(project_id: ProjectId, db: DB, actor: Actor, hours: int = Query(24, ge=1, le=168)):
    project_scope(db, actor, str(project_id))
    start, end = time_bounds(hours)
    spans = list(
        db.scalars(
            select(Span)
            .where(
                *scope(Span, actor.organization_id, str(project_id)),
                Span.start_ns.between(start, end),
            )
            .limit(10001)
        )
    )
    if len(spans) > 10000:
        fail(
            422,
            "WINDOW_TOO_LARGE",
            "Select a smaller time window; maximum 10,000 spans.",
        )
    lookup = {(s.trace_id, s.span_id): s for s in spans}
    edges = set()
    for s in spans:
        parent = lookup.get((s.trace_id, s.parent_span_id))
        if parent and parent.service != s.service:
            edges.add((parent.service, s.service))
    items = []
    for name in sorted({s.service for s in spans}):
        group = [s for s in spans if s.service == name]
        errors = sum(s.status == "error" for s in group)
        items.append(
            {
                "name": name,
                "calls": len(group),
                "errors": errors,
                "p95_ms": percentile([(s.end_ns - s.start_ns) / 1e6 for s in group if s.end_ns], 0.95),
                "status": "degraded" if errors else "observed",
                "last_seen": max(s.ingested_at for s in group),
            }
        )
    return {
        "items": items,
        "edges": [
            {"source": a, "target": b, "provenance": "observed parent-child span"} for a, b in sorted(edges)
        ],
    }


@app.get("/v1/rules", response_model=contract.Page[contract.RuleView])
def rules(project_id: ProjectId, db: DB, actor: Actor):
    return listing(db, actor, Rule, str(project_id), 100)


@app.post("/v1/rules", status_code=201, response_model=contract.RuleView)
def create_rule(body: RuleInput, project_id: ProjectId, request: Request, db: DB, actor: Actor):
    require(actor, "admin", "operator", "developer")
    project_scope(db, actor, str(project_id))
    if body.metric == "error_rate" and body.threshold > 100:
        fail(
            422,
            "INVALID_THRESHOLD",
            "Error rate threshold is a percentage from 0 to 100.",
        )
    if body.detector != "threshold" and body.min_samples < 3:
        fail(422, "MINIMUM_SAMPLES", "Statistical detectors require at least three samples.")
    if (
        db.scalar(
            select(func.count()).select_from(Rule).where(*scope(Rule, actor.organization_id, str(project_id)))
        )
        >= 100
    ):
        fail(429, "RULE_QUOTA", "Maximum 100 rules per project.")
    rule = Rule(
        organization_id=actor.organization_id,
        project_id=str(project_id),
        **body.model_dump(),
    )
    db.add(rule)
    flush(db)
    db.add(
        RuleVersion(
            organization_id=actor.organization_id,
            project_id=str(project_id),
            rule_id=rule.id,
            version=rule.version,
            manifest={**body.model_dump(), "enabled": True},
        )
    )
    db.add(
        Job(
            organization_id=actor.organization_id,
            project_id=str(project_id),
            kind="detect",
            resource_id=rule.id,
        )
    )
    audit(
        db,
        actor.organization_id,
        actor.subject,
        "rule.created",
        rule.id,
        request.state.request_id,
        project_id=str(project_id),
    )
    commit(db)
    return serialize(rule)


@app.post("/v1/rules/preview", response_model=contract.RulePreviewView)
def preview_rule(body: RuleInput, project_id: ProjectId, db: DB, actor: Actor):
    require(actor, "admin", "operator", "developer")
    project_scope(db, actor, str(project_id))
    if body.metric == "error_rate" and body.threshold > 100:
        fail(422, "INVALID_THRESHOLD", "Error rate threshold is a percentage from 0 to 100.")
    if body.detector != "threshold" and body.min_samples < 3:
        fail(422, "MINIMUM_SAMPLES", "Statistical detectors require at least three samples.")
    end = now()
    start = end - timedelta(minutes=body.window_minutes)
    traces = list(
        db.scalars(
            select(Trace)
            .where(
                *scope(Trace, actor.organization_id, str(project_id)),
                Trace.start_ns.between(int(start.timestamp() * 1e9), int(end.timestamp() * 1e9)),
                Trace.status != "incomplete",
            )
            .order_by(Trace.start_ns, Trace.id)
            .limit(10_001)
        )
    )
    oversized = len(traces) > 10_000
    rule = Rule(organization_id=actor.organization_id, project_id=str(project_id), **body.model_dump())
    result = detection_result(rule, traces[:10_000], oversized)
    return {
        **{key: result[key] for key in ("state", "observed", "baseline", "deviation", "anomaly_score", "sample_count")},
        "detector": body.detector,
        "would_fire": result["firing"],
        "limitations": "Dry-run over the current bounded telemetry window; it does not create a detection or incident.",
    }


@app.get("/v1/rules/{identifier}", response_model=contract.RuleView)
def get_rule(identifier: UUID, project_id: ProjectId, db: DB, actor: Actor):
    project_scope(db, actor, str(project_id))
    return serialize(scoped(db, actor, Rule, str(identifier), str(project_id)))


@app.patch("/v1/rules/{identifier}", response_model=contract.RuleView)
def patch_rule(
    identifier: UUID,
    body: RulePatch,
    project_id: ProjectId,
    request: Request,
    db: DB,
    actor: Actor,
):
    require(actor, "admin", "operator", "developer")
    rule = scoped(db, actor, Rule, str(identifier), str(project_id))
    db.refresh(rule, with_for_update=True)
    metric = body.metric if body.metric is not None else rule.metric
    detector = body.detector if body.detector is not None else rule.detector
    threshold = body.threshold if body.threshold is not None else rule.threshold
    min_samples = body.min_samples if body.min_samples is not None else rule.min_samples
    if metric == "error_rate" and threshold > 100:
        fail(422, "INVALID_THRESHOLD", "Error rate threshold is a percentage from 0 to 100.")
    if detector != "threshold" and min_samples < 3:
        fail(422, "MINIMUM_SAMPLES", "Statistical detectors require at least three samples.")

    updates = body.model_dump(exclude_unset=True)
    if not updates:
        return serialize(rule)

    for field, val in updates.items():
        setattr(rule, field, val)
    rule.version += 1

    db.add(
        RuleVersion(
            organization_id=actor.organization_id,
            project_id=str(project_id),
            rule_id=rule.id,
            version=rule.version,
            manifest=serialize(rule),
        )
    )
    db.add(
        Job(
            organization_id=actor.organization_id,
            project_id=str(project_id),
            kind="detect",
            resource_id=rule.id,
        )
    )
    audit(
        db,
        actor.organization_id,
        actor.subject,
        f"rule.version.{rule.version}",
        rule.id,
        request.state.request_id,
        project_id=str(project_id),
    )
    commit(db)
    return serialize(rule)


@app.delete("/v1/rules/{identifier}", status_code=204)
def delete_rule(
    identifier: UUID,
    project_id: ProjectId,
    request: Request,
    db: DB,
    actor: Actor,
):
    require(actor, "admin", "operator", "developer")
    rule = scoped(db, actor, Rule, str(identifier), str(project_id))
    db.refresh(rule, with_for_update=True)
    if (
        db.scalar(
            select(func.count()).select_from(Incident).where(
                *scope(Incident, actor.organization_id, str(project_id)),
                Incident.rule_id == rule.id,
            )
        )
        > 0
    ):
        fail(409, "RULE_IN_USE", "Cannot delete rule with linked incidents. Disable the rule instead.")
    rule.deleted_at = now()
    rule.enabled = False
    audit(
        db,
        actor.organization_id,
        actor.subject,
        "rule.deleted",
        rule.id,
        request.state.request_id,
        project_id=str(project_id),
    )
    commit(db)
    return Response(status_code=204)


@app.get("/v1/detections", response_model=contract.Page[contract.DetectionView])
def detections(
    project_id: ProjectId,
    db: DB,
    actor: Actor,
    limit: PageLimit = 50,
    cursor: UUID | None = None,
    state: Literal["NORMAL", "ANOMALY", "INSUFFICIENT_DATA"] | None = None,
    detector: Literal["threshold", "ewma", "robust_mad"] | None = None,
):
    project_scope(db, actor, str(project_id))
    query = select(Detection).where(*scope(Detection, actor.organization_id, str(project_id)))
    if state:
        query = query.where(Detection.state == state)
    if detector:
        query = query.where(Detection.detector == detector)
    if cursor:
        query = query.where(Detection.id < str(cursor))
    rows = list(db.scalars(query.order_by(Detection.id.desc()).limit(limit + 1)))
    return {
        "items": [serialize(row) for row in rows[:limit]],
        "next_cursor": rows[limit - 1].id if len(rows) > limit else None,
    }


def serialize_slo(db: DB, slo: SLO, trend_limit: int = 24):
    snapshots = list(
        db.scalars(
            select(SLOSnapshot)
            .where(
                *scope(SLOSnapshot, slo.organization_id, slo.project_id),
                SLOSnapshot.slo_id == slo.id,
            )
            .order_by(SLOSnapshot.calculated_at.desc())
            .limit(trend_limit)
        )
    )
    return {
        **serialize(slo),
        "latest": serialize(snapshots[0]) if snapshots else None,
        "trend": [serialize(snapshot) for snapshot in reversed(snapshots)],
    }


@app.get("/v1/slos", response_model=contract.Page[contract.SLOView])
def slos(project_id: ProjectId, db: DB, actor: Actor):
    project_scope(db, actor, str(project_id))
    rows = list(
        db.scalars(
            select(SLO)
            .where(*scope(SLO, actor.organization_id, str(project_id)))
            .order_by(SLO.created_at.desc(), SLO.id.desc())
            .limit(51)
        )
    )
    return {"items": [serialize_slo(db, slo) for slo in rows[:50]], "next_cursor": None}


@app.post("/v1/slos", status_code=201, response_model=contract.SLOView)
def create_slo(body: SLOInput, project_id: ProjectId, request: Request, db: DB, actor: Actor):
    require(actor, "admin", "operator", "developer")
    project_scope(db, actor, str(project_id))
    if body.sli == "latency" and body.latency_threshold_ms is None:
        fail(422, "LATENCY_THRESHOLD_REQUIRED", "Latency SLOs require a latency threshold.")
    if body.sli == "success_rate" and body.latency_threshold_ms is not None:
        fail(422, "INVALID_SLO", "Success-rate SLOs do not accept a latency threshold.")
    if not body.short_window_minutes < body.long_window_minutes <= body.window_minutes:
        fail(422, "INVALID_WINDOWS", "Require short window < long window <= objective window.")
    if (
        db.scalar(select(func.count()).select_from(SLO).where(*scope(SLO, actor.organization_id, str(project_id))))
        >= 50
    ):
        fail(429, "SLO_QUOTA", "Maximum 50 SLOs per project.")
    slo = SLO(organization_id=actor.organization_id, project_id=str(project_id), **body.model_dump())
    db.add(slo)
    flush(db)
    db.add(
        Job(
            organization_id=actor.organization_id,
            project_id=str(project_id),
            kind="detect",
            resource_id=slo.id,
        )
    )
    audit(
        db,
        actor.organization_id,
        actor.subject,
        "slo.created",
        slo.id,
        request.state.request_id,
        project_id=str(project_id),
    )
    commit(db)
    return serialize_slo(db, slo)


@app.patch("/v1/slos/{identifier}", response_model=contract.SLOView)
def toggle_slo(
    identifier: UUID,
    body: SLOToggle,
    project_id: ProjectId,
    request: Request,
    db: DB,
    actor: Actor,
):
    require(actor, "admin", "operator", "developer")
    slo = scoped(db, actor, SLO, str(identifier), str(project_id))
    slo.enabled = body.enabled
    audit(
        db,
        actor.organization_id,
        actor.subject,
        "slo.enabled" if body.enabled else "slo.disabled",
        slo.id,
        request.state.request_id,
        project_id=str(project_id),
    )
    commit(db)
    return serialize_slo(db, slo)


@app.get("/v1/changes", response_model=contract.Page[contract.ChangeEventView])
def changes(project_id: ProjectId, db: DB, actor: Actor, limit: PageLimit = 50):
    return listing(db, actor, ChangeEvent, str(project_id), limit)


@app.post("/v1/changes", status_code=201, response_model=contract.ChangeEventView)
def create_change(
    body: ChangeEventInput,
    project_id: ProjectId,
    request: Request,
    db: DB,
    actor: Actor,
):
    require(actor, "admin", "operator", "developer")
    project_scope(db, actor, str(project_id))
    recorded = body.recorded_at
    if recorded.tzinfo is None:
        fail(422, "TIMEZONE_REQUIRED", "recorded_at must include a timezone offset.")
    if recorded > now() + timedelta(minutes=5) or recorded < now() - timedelta(days=30):
        fail(422, "INVALID_CHANGE_TIME", "Change time must be within the last 30 days and not in the future.")
    if (
        db.scalar(
            select(func.count()).select_from(ChangeEvent).where(
                *scope(ChangeEvent, actor.organization_id, str(project_id))
            )
        )
        >= 1000
    ):
        fail(429, "CHANGE_QUOTA", "Maximum 1,000 retained change events per project.")
    event = ChangeEvent(
        organization_id=actor.organization_id,
        project_id=str(project_id),
        **body.model_dump(),
    )
    db.add(event)
    flush(db)
    active = list(
        db.scalars(
            select(Incident)
            .where(
                *scope(Incident, actor.organization_id, str(project_id)),
                Incident.status != "RESOLVED",
                Incident.created_at >= recorded - timedelta(minutes=5),
                Incident.created_at <= recorded + timedelta(minutes=60),
            )
            .limit(100)
        )
    )
    outstanding = db.scalar(
        select(func.count()).select_from(Job).where(
            *scope(Job, actor.organization_id, str(project_id)), Job.status.in_(["QUEUED", "RUNNING"])
        )
    )
    if outstanding + len(active) > 1000:
        fail(429, "QUEUE_SATURATED", "Processing backlog reached its bound. Retry with backoff.")
    for incident in active:
        queue_diagnosis(db, incident)
    audit(
        db,
        actor.organization_id,
        actor.subject,
        "change.recorded",
        event.id,
        request.state.request_id,
        project_id=str(project_id),
    )
    commit(db)
    return serialize(event)


@app.get("/v1/incidents", response_model=contract.Page[contract.IncidentView])
def incidents(
    project_id: ProjectId,
    db: DB,
    actor: Actor,
    limit: PageLimit = 50,
    cursor: UUID | None = None,
    status: Literal["OPEN", "ACKNOWLEDGED", "RESOLVED", "active"] | None = None,
    severity: Literal["critical", "high", "medium", "low"] | None = None,
):
    project_scope(db, actor, str(project_id))
    query = select(Incident).where(*scope(Incident, actor.organization_id, str(project_id)))
    if status:
        query = query.where(
            Incident.status != "RESOLVED" if status == "active" else Incident.status == status
        )
    if severity:
        query = query.where(Incident.severity == severity)
    if cursor:
        query = query.where(Incident.id < str(cursor))
    rows = list(db.scalars(query.order_by(Incident.id.desc()).limit(limit + 1)))
    return {
        "items": [serialize(i) for i in rows[:limit]],
        "next_cursor": rows[limit - 1].id if len(rows) > limit else None,
    }


@app.get("/v1/incidents/{identifier}", response_model=contract.IncidentView)
def incident_detail(identifier: UUID, project_id: ProjectId, db: DB, actor: Actor):
    return serialize(scoped(db, actor, Incident, str(identifier), str(project_id)))


@app.patch("/v1/incidents/{identifier}", response_model=contract.IncidentView)
def update_incident(
    identifier: UUID,
    body: IncidentPatch,
    project_id: ProjectId,
    request: Request,
    db: DB,
    actor: Actor,
):
    require(actor, "admin", "operator")
    incident = scoped(db, actor, Incident, str(identifier), str(project_id))
    db.refresh(incident, with_for_update=True)
    allowed = {
        "OPEN": {"ACKNOWLEDGED", "RESOLVED"},
        "ACKNOWLEDGED": {"OPEN", "RESOLVED"},
        "RESOLVED": {"OPEN"},
    }
    if body.status != incident.status:
        if body.status not in allowed[incident.status]:
            fail(409, "INVALID_TRANSITION", "Incident transition is not permitted.")
        incident.status, incident.updated_at = body.status, now()
        incident.timeline = [
            *incident.timeline,
            {
                "action": body.status.lower(),
                "actor": actor.name,
                "at": now().isoformat(),
            },
        ]
        audit(
            db,
            actor.organization_id,
            actor.subject,
            f"incident.{body.status.lower()}",
            incident.id,
            request.state.request_id,
            project_id=str(project_id),
        )
        commit(db)
    return serialize(incident)


@app.get("/v1/incidents/{identifier}/hypotheses", response_model=contract.HypothesesView)
def hypotheses(identifier: UUID, project_id: ProjectId, db: DB, actor: Actor):
    incident = scoped(db, actor, Incident, str(identifier), str(project_id))
    rows = list(
        db.scalars(
            select(Hypothesis)
            .where(
                *scope(Hypothesis, actor.organization_id, str(project_id)),
                Hypothesis.incident_id == incident.id,
            )
            .order_by(Hypothesis.rank)
        )
    )
    items = []
    for row in rows:
        evidence_rows = list(
            db.scalars(
                select(EvidenceLink)
                .where(
                    *scope(EvidenceLink, actor.organization_id, str(project_id)),
                    EvidenceLink.hypothesis_id == row.id,
                )
                .order_by(EvidenceLink.trace_id, EvidenceLink.span_id)
            )
        )
        items.append(
            {
                **serialize(row, {"organization_id", "project_id", "incident_id", "created_at"}),
                "supporting": [
                    {
                        "trace_id": evidence.trace_id,
                        "span_id": evidence.span_id,
                        "operation": evidence.operation,
                    }
                    for evidence in evidence_rows
                    if evidence.kind == "supporting"
                ],
                "contradicting": [
                    {
                        "trace_id": evidence.trace_id,
                        "span_id": evidence.span_id,
                        "operation": evidence.operation,
                    }
                    for evidence in evidence_rows
                    if evidence.kind == "contradicting"
                ],
            }
        )
    diagnosis_job = db.scalar(
        select(Job)
        .where(
            *scope(Job, actor.organization_id, str(project_id)),
            Job.kind == "diagnosis",
            Job.resource_id == incident.id,
        )
        .order_by(Job.available_at.desc())
        .limit(1)
    )
    state = (
        "partial"
        if items
        else "processing"
        if diagnosis_job and diagnosis_job.status in {"QUEUED", "RUNNING"}
        else "error"
        if diagnosis_job and diagnosis_job.status == "DEAD_LETTER"
        else "INSUFFICIENT_EVIDENCE"
    )
    return {
        "items": items,
        "state": state,
        "limitations": "Failure propagation analysis is bounded to 5,000 linked spans and recorded changes within the correlation window. Temporal and dependency correlation do not prove causation; controlled recovery evidence remains unavailable.",
    }


@app.get("/v1/incidents/{identifier}/notes", response_model=contract.Page[contract.IncidentNoteView])
def incident_notes(identifier: UUID, project_id: ProjectId, db: DB, actor: Actor):
    incident = scoped(db, actor, Incident, str(identifier), str(project_id))
    rows = list(
        db.scalars(
            select(IncidentNote)
            .where(
                *scope(IncidentNote, actor.organization_id, str(project_id)),
                IncidentNote.incident_id == incident.id,
            )
            .order_by(IncidentNote.created_at.asc())
        )
    )
    return {
        "items": [serialize(row) for row in rows],
        "next_cursor": None,
    }


@app.post("/v1/incidents/{identifier}/notes", status_code=201, response_model=contract.IncidentNoteView)
def create_incident_note(
    identifier: UUID,
    body: IncidentNoteInput,
    project_id: ProjectId,
    request: Request,
    db: DB,
    actor: Actor,
):
    require(actor, "admin", "operator", "developer")
    incident = scoped(db, actor, Incident, str(identifier), str(project_id))
    content = body.content.strip()
    if not content:
        fail(422, "EMPTY_NOTE", "Note content cannot be empty.")
    note = IncidentNote(
        organization_id=actor.organization_id,
        project_id=str(project_id),
        incident_id=incident.id,
        author_name=actor.name,
        author_subject=actor.subject,
        content=content,
    )
    db.add(note)
    audit(
        db,
        actor.organization_id,
        actor.subject,
        "incident.note.created",
        incident.id,
        request.state.request_id,
        project_id=str(project_id),
    )
    commit(db)
    return serialize(note)


@app.get("/v1/datasets", response_model=contract.Page[contract.DatasetView])
def datasets(project_id: ProjectId, db: DB, actor: Actor):
    page = listing(db, actor, Dataset, str(project_id), 100)
    for item in page["items"]:
        dataset = scoped(db, actor, Dataset, item["id"], str(project_id))
        item["case_count"] = len(dataset.cases)
    return page


@app.post("/v1/datasets", status_code=201, response_model=contract.DatasetView)
def publish_dataset(body: DatasetInput, project_id: ProjectId, request: Request, db: DB, actor: Actor):
    require(actor, "admin", "developer")
    project_scope(db, actor, str(project_id))
    db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:scope, 0))"),
        {"scope": f"datasets:{actor.organization_id}:{project_id}"},
    )
    if len({c.id for c in body.cases}) != len(body.cases):
        fail(422, "DUPLICATE_CASE", "Case identifiers must be unique.")
    if (
        db.scalar(
            select(func.count())
            .select_from(Dataset)
            .where(*scope(Dataset, actor.organization_id, str(project_id)))
        )
        >= 100
    ):
        fail(429, "DATASET_QUOTA", "Maximum 100 immutable datasets per project.")
    cases = [case.model_dump() for case in body.cases]
    dataset = Dataset(
        organization_id=actor.organization_id,
        project_id=str(project_id),
        name=body.name,
        description=body.description,
        version=1,
        cases=cases,
        manifest_hash=manifest_hash(cases),
    )
    db.add(dataset)
    flush(db)
    audit(
        db,
        actor.organization_id,
        actor.subject,
        "dataset.published",
        dataset.id,
        request.state.request_id,
        project_id=str(project_id),
    )
    commit(db)
    return {**serialize(dataset, {"cases"}), "case_count": len(cases)}


@app.get("/v1/datasets/{identifier}", response_model=contract.DatasetView)
def dataset_detail(identifier: UUID, project_id: ProjectId, db: DB, actor: Actor):
    dataset = scoped(db, actor, Dataset, str(identifier), str(project_id))
    return {**serialize(dataset), "case_count": len(dataset.cases)}


@app.get("/v1/datasets/{identifier}/versions", response_model=contract.Page[contract.DatasetView])
def dataset_versions(identifier: UUID, project_id: ProjectId, db: DB, actor: Actor):
    dataset = scoped(db, actor, Dataset, str(identifier), str(project_id))
    root_id = dataset.parent_id or dataset.id
    versions = db.scalars(
        select(Dataset)
        .where(
            *scope(Dataset, actor.organization_id, str(project_id)),
            (Dataset.id == root_id) | (Dataset.parent_id == root_id),
        )
        .order_by(Dataset.version.desc())
    ).all()
    return {
        "items": [
            {**serialize(d, {"cases"}), "case_count": len(d.cases)}
            for d in versions
        ]
    }


@app.post("/v1/datasets/{identifier}/versions", status_code=201, response_model=contract.DatasetView)
def publish_dataset_version(
    identifier: UUID,
    body: DatasetVersionInput,
    project_id: ProjectId,
    request: Request,
    db: DB,
    actor: Actor,
):
    require(actor, "admin", "developer")
    project_scope(db, actor, str(project_id))
    dataset = scoped(db, actor, Dataset, str(identifier), str(project_id))
    root_id = dataset.parent_id or dataset.id
    root = scoped(db, actor, Dataset, root_id, str(project_id))

    db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:scope, 0))"),
        {"scope": f"datasets:{actor.organization_id}:{project_id}"},
    )
    if len({c.id for c in body.cases}) != len(body.cases):
        fail(422, "DUPLICATE_CASE", "Case identifiers must be unique.")
    if (
        db.scalar(
            select(func.count())
            .select_from(Dataset)
            .where(*scope(Dataset, actor.organization_id, str(project_id)))
        )
        >= 100
    ):
        fail(429, "DATASET_QUOTA", "Maximum 100 immutable datasets per project.")

    max_version = (
        db.scalar(
            select(func.max(Dataset.version)).where(
                *scope(Dataset, actor.organization_id, str(project_id)),
                (Dataset.id == root_id) | (Dataset.parent_id == root_id),
            )
        )
        or 1
    )
    cases = [case.model_dump() for case in body.cases]
    new_version = Dataset(
        organization_id=actor.organization_id,
        project_id=str(project_id),
        name=root.name,
        description=body.description or root.description,
        parent_id=root_id,
        version=max_version + 1,
        cases=cases,
        manifest_hash=manifest_hash(cases),
    )
    db.add(new_version)
    flush(db)
    audit(
        db,
        actor.organization_id,
        actor.subject,
        "dataset.version.published",
        new_version.id,
        request.state.request_id,
        project_id=str(project_id),
    )
    commit(db)
    return {**serialize(new_version, {"cases"}), "case_count": len(cases)}


@app.get("/v1/evaluations", response_model=contract.Page[contract.EvaluationView])
def evaluations(
    project_id: ProjectId,
    db: DB,
    actor: Actor,
    limit: PageLimit = 50,
    cursor: UUID | None = None,
):
    return listing(db, actor, Evaluation, str(project_id), limit, cursor)


@app.post("/v1/evaluations", status_code=202, response_model=contract.EvaluationView)
def create_evaluation(
    body: EvaluationInput,
    project_id: ProjectId,
    request: Request,
    db: DB,
    actor: Actor,
    idempotency_key: Annotated[str | None, Header()] = None,
):
    require(actor, "admin", "developer")
    dataset = scoped(db, actor, Dataset, str(body.dataset_id), str(project_id))
    if body.mode != "offline-paired-replay" or body.candidate_code is not None:
        fail(503, "EVALUATOR_UNAVAILABLE", "Isolated code execution is unavailable; use offline paired replay.")
    key = idempotency(idempotency_key)
    request_hash = manifest_hash(body.model_dump(mode="json"))
    existing = db.scalar(
        select(Evaluation).where(
            *scope(Evaluation, actor.organization_id, str(project_id)),
            Evaluation.idempotency_key == key,
        )
    )
    if existing:
        if existing.request_hash != request_hash:
            fail(409, "IDEMPOTENCY_CONFLICT", "Key already used for a different request.")
        return serialize(existing)
    pending = db.scalar(
        select(func.count())
        .select_from(Evaluation)
        .where(
            *scope(Evaluation, actor.organization_id, str(project_id)),
            Evaluation.status.in_(["QUEUED", "RUNNING"]),
        )
    )
    if pending >= 10:
        fail(429, "RUN_QUOTA", "At most 10 outstanding evaluations per project.")
    manifest = {
        "dataset_version": dataset.version,
        "dataset_hash": dataset.manifest_hash,
        "baseline": body.baseline,
        "candidate": body.candidate,
        "grader": body.grader,
        "mode": body.mode,
        "repeats": body.repeats,
        "safety_patterns": body.safety_patterns or [],
        "latency_budget_ms": body.latency_budget_ms,
        "cost_budget_tokens": body.cost_budget_tokens,
        "candidate_code": body.candidate_code,
        "max_cases": 500,
        "network": "none",
        "minimum_samples": 30,
    }
    run = Evaluation(
        organization_id=actor.organization_id,
        project_id=str(project_id),
        dataset_id=dataset.id,
        idempotency_key=key,
        request_hash=request_hash,
        baseline=body.baseline,
        candidate=body.candidate,
        manifest=manifest,
    )
    db.add(run)
    flush(db)
    db.add(
        Job(
            organization_id=actor.organization_id,
            project_id=str(project_id),
            kind="evaluation",
            resource_id=run.id,
        )
    )
    audit(
        db,
        actor.organization_id,
        actor.subject,
        "evaluation.queued",
        run.id,
        request.state.request_id,
        project_id=str(project_id),
    )
    commit(db)
    return serialize(run)


@app.get("/v1/evaluations/{identifier}", response_model=contract.EvaluationView)
def evaluation_detail(identifier: UUID, project_id: ProjectId, db: DB, actor: Actor):
    return serialize(scoped(db, actor, Evaluation, str(identifier), str(project_id)))


@app.get("/v1/evaluations/{identifier}/export", response_model=contract.EvaluationReportView)
def export_evaluation(identifier: UUID, project_id: ProjectId, request: Request, db: DB, actor: Actor):
    require(actor, "admin", "developer", "operator")
    run = scoped(db, actor, Evaluation, str(identifier), str(project_id))
    if run.status not in {"COMPLETED", "FAILED"}:
        fail(409, "RUN_NOT_FINISHED", "Wait for the evaluation to finish before exporting its report.")
    report_content = {
        "id": run.id,
        "organization_id": run.organization_id,
        "project_id": run.project_id,
        "dataset_id": run.dataset_id,
        "dataset_version": run.manifest.get("dataset_version", 1),
        "dataset_hash": run.manifest.get("dataset_hash", ""),
        "baseline": run.baseline,
        "candidate": run.candidate,
        "status": run.status,
        "decision": run.decision,
        "created_at": run.created_at,
        "manifest": run.manifest,
        "results": run.results,
    }
    # Hash the exact public JSON representation, including response-model defaults.
    report_content = contract.EvaluationReportView(
        **report_content, report_checksum=""
    ).model_dump(mode="json", exclude={"report_checksum"})
    report_checksum = manifest_hash(report_content)
    audit(
        db,
        actor.organization_id,
        actor.subject,
        "evaluation.exported",
        run.id,
        request.state.request_id,
        project_id=str(project_id),
    )
    commit(db)
    return {**report_content, "report_checksum": report_checksum}


@app.get("/v1/remediations", response_model=contract.RemediationsView)
def remediations(project_id: ProjectId, db: DB, actor: Actor):
    return {
        **listing(db, actor, Remediation, str(project_id), 100),
        "execution_enabled": False,
        "disabled_reason": "An isolated executor, target preconditions, post-checks and rollback adapter must be configured and verified.",
    }


@app.post("/v1/remediations", status_code=201, response_model=contract.RemediationView)
def propose_remediation(
    body: ProposalInput,
    project_id: ProjectId,
    request: Request,
    db: DB,
    actor: Actor,
    idempotency_key: Annotated[str | None, Header()] = None,
):
    require(actor, "admin", "operator")
    incident = scoped(db, actor, Incident, str(body.incident_id), str(project_id))
    key = idempotency(idempotency_key)
    project = project_scope(db, actor, str(project_id))
    manifest = {
        **body.model_dump(mode="json"),
        "environment": project.environment,
        "project_id": project.id,
        "evidence": incident.evidence,
        "risk": "high",
        "validation": "BLOCKED_NO_EXECUTOR",
    }
    existing = db.scalar(
        select(Remediation).where(
            *scope(Remediation, actor.organization_id, project.id),
            Remediation.idempotency_key == key,
        )
    )
    if existing:
        if any(existing.manifest.get(key) != value for key, value in body.model_dump(mode="json").items()):
            fail(409, "IDEMPOTENCY_CONFLICT", "Key already used for another manifest.")
        return serialize(existing)
    proposal = Remediation(
        organization_id=actor.organization_id,
        project_id=project.id,
        incident_id=incident.id,
        proposer=actor.subject,
        idempotency_key=key,
        manifest=manifest,
        manifest_hash=manifest_hash(manifest),
        expires_at=now() + timedelta(minutes=body.expires_minutes),
    )
    db.add(proposal)
    flush(db)
    audit(
        db,
        actor.organization_id,
        actor.subject,
        "remediation.proposed",
        proposal.id,
        request.state.request_id,
        project_id=str(project_id),
    )
    commit(db)
    return serialize(proposal)


@app.get("/v1/remediations/{identifier}", response_model=contract.RemediationView)
def remediation_detail(identifier: UUID, project_id: ProjectId, db: DB, actor: Actor):
    return {
        **serialize(scoped(db, actor, Remediation, str(identifier), str(project_id))),
        "execution_enabled": False,
        "disabled_reason": "Remote execution is disabled; validation cannot run without an isolated target adapter.",
    }


@app.post("/v1/remediations/{identifier}/reject", response_model=contract.RemediationView)
def reject_remediation(identifier: UUID, project_id: ProjectId, request: Request, db: DB, actor: Actor):
    require(actor, "admin", "operator", "approver")
    proposal = scoped(db, actor, Remediation, str(identifier), str(project_id))
    db.refresh(proposal, with_for_update=True)
    if proposal.state == "REJECTED":
        return serialize(proposal)
    if proposal.state not in {"PROPOSED", "VALIDATED", "APPROVED"}:
        fail(409, "INVALID_TRANSITION", "Proposal cannot be rejected in this state.")
    proposal.state = "REJECTED"
    audit(
        db,
        actor.organization_id,
        actor.subject,
        "remediation.rejected",
        proposal.id,
        request.state.request_id,
        project_id=str(project_id),
    )
    commit(db)
    return serialize(proposal)


@app.post("/v1/remediations/{identifier}/approve")
def approve_remediation(
    identifier: UUID,
    body: ApprovalInput,
    project_id: ProjectId,
    request: Request,
    db: DB,
    actor: Actor,
):
    require(actor, "approver")
    proposal = scoped(db, actor, Remediation, str(identifier), str(project_id))
    if proposal.proposer == actor.subject:
        fail(
            403,
            "INDEPENDENT_APPROVER_REQUIRED",
            "A different identity must approve the manifest.",
        )
    if (
        proposal.manifest_hash != body.manifest_hash
        or proposal.expires_at <= now()
        or proposal.state != "VALIDATED"
    ):
        fail(
            409,
            "INVALID_APPROVAL",
            "Manifest must be current, unexpired and independently validated.",
        )
    audit(
        db,
        actor.organization_id,
        actor.subject,
        "remediation.approval_denied",
        proposal.id,
        request.state.request_id,
        "denied",
        project_id=str(project_id),
    )
    commit(db)
    fail(
        503,
        "EXECUTOR_DISABLED",
        "Approval is blocked until isolated executor validation is available.",
    )


@app.post("/v1/remediations/{identifier}/execute")
def execute_remediation(identifier: UUID, project_id: ProjectId, request: Request, db: DB, actor: Actor):
    require(actor, "executor")
    proposal = scoped(db, actor, Remediation, str(identifier), str(project_id))
    audit(
        db,
        actor.organization_id,
        actor.subject,
        "remediation.execution_denied",
        proposal.id,
        request.state.request_id,
        "denied",
        project_id=str(project_id),
    )
    commit(db)
    fail(
        503,
        "EXECUTOR_DISABLED",
        "Remote actions are disabled. No mutation was scheduled.",
    )


@app.get("/v1/audit", response_model=contract.Page[contract.AuditView])
def audit_log(
    db: DB,
    actor: Actor,
    project_id: ProjectId | None = None,
    limit: PageLimit = 50,
    cursor: UUID | None = None,
):
    require(actor, "admin", "operator", "approver")
    query = select(AuditEvent).where(AuditEvent.organization_id == actor.organization_id)
    if project_id is not None:
        project_scope(db, actor, str(project_id))
        query = query.where(AuditEvent.project_id == str(project_id))
    elif actor.role != "admin":
        fail(422, "PROJECT_REQUIRED", "A project scope is required for this role.")
    if cursor:
        query = query.where(AuditEvent.id < str(cursor))
    rows = list(db.scalars(query.order_by(AuditEvent.id.desc()).limit(limit + 1)))
    return {
        "items": [serialize(r) for r in rows[:limit]],
        "next_cursor": rows[limit - 1].id if len(rows) > limit else None,
    }


@app.get("/v1/exports/summary")
def export_summary(
    project_id: ProjectId,
    request: Request,
    db: DB,
    actor: Actor,
    hours: int = Query(24, ge=1, le=168),
):
    require(actor, "admin", "operator")
    data = metrics(project_id, db, actor, hours)
    audit(
        db,
        actor.organization_id,
        actor.subject,
        "metrics.exported",
        str(project_id),
        request.state.request_id,
        project_id=str(project_id),
    )
    commit(db)
    return Response(
        json.dumps(data, default=str),
        media_type="application/json",
        headers={"Content-Disposition": 'attachment; filename="neuralops-summary.json"'},
    )


@app.get("/v1/analytics", response_model=contract.AnalyticsView)
def analytics(project_id: ProjectId, db: DB, actor: Actor, hours: int = Query(24, ge=1, le=168)):
    project_scope(db, actor, str(project_id))
    start, end = time_bounds(hours)
    spans = list(
        db.scalars(
            select(Span)
            .where(
                *scope(Span, actor.organization_id, str(project_id)),
                Span.start_ns.between(start, end),
            )
            .limit(10001)
        )
    )
    if len(spans) > 10000:
        fail(
            422,
            "WINDOW_TOO_LARGE",
            "Select a smaller time window; maximum 10,000 spans.",
        )

    def usage(group, key):
        values = [s.attributes[key] for s in group if key in s.attributes]
        return sum(values) if values else None

    def summary(group):
        return {
            "calls": len(group),
            "errors": sum(s.status == "error" for s in group),
            "p95_ms": percentile([(s.end_ns - s.start_ns) / 1e6 for s in group if s.end_ns], 0.95),
        }

    model_keys = sorted(
        {
            (
                s.attributes.get("gen_ai.provider.name", s.attributes.get("gen_ai.system", "unknown")),
                s.attributes.get("gen_ai.request.model", s.attributes.get("gen_ai.response.model")),
            )
            for s in spans
            if s.attributes.get("gen_ai.request.model") or s.attributes.get("gen_ai.response.model")
        }
    )
    models = []
    for provider, model in model_keys:
        group = [
            s
            for s in spans
            if s.attributes.get("gen_ai.request.model", s.attributes.get("gen_ai.response.model")) == model
            and s.attributes.get("gen_ai.provider.name", s.attributes.get("gen_ai.system", "unknown"))
            == provider
        ]
        models.append(
            {
                "provider": provider,
                "model": model,
                **summary(group),
                "input_tokens": usage(group, "gen_ai.usage.input_tokens"),
                "output_tokens": usage(group, "gen_ai.usage.output_tokens"),
            }
        )
    tools = []
    for name in sorted(
        {
            s.attributes.get("gen_ai.tool.name", s.operation)
            for s in spans
            if s.attributes.get("gen_ai.operation.name") == "execute_tool"
        }
    ):
        group = [
            s
            for s in spans
            if s.attributes.get("gen_ai.operation.name") == "execute_tool"
            and s.attributes.get("gen_ai.tool.name", s.operation) == name
        ]
        tools.append({"name": name, **summary(group)})
    return {
        "models": models,
        "tools": tools,
        "input_tokens": usage(spans, "gen_ai.usage.input_tokens"),
        "output_tokens": usage(spans, "gen_ai.usage.output_tokens"),
        "span_count": len(spans),
        "usage_coverage": sum(
            any(k in s.attributes for k in ("gen_ai.usage.input_tokens", "gen_ai.usage.output_tokens"))
            for s in spans
        ),
    }


@app.get("/v1/rules/{identifier}/versions", response_model=contract.Page[contract.RuleVersionView])
def rule_versions(identifier: UUID, project_id: ProjectId, db: DB, actor: Actor):
    rule = scoped(db, actor, Rule, str(identifier), str(project_id))
    versions = db.scalars(
        select(RuleVersion)
        .where(*scope(RuleVersion, actor.organization_id, str(project_id)), RuleVersion.rule_id == rule.id)
        .order_by(RuleVersion.version)
    ).all()
    return {"items": [serialize(v) for v in versions]}


@app.patch("/v1/projects/{identifier}", response_model=contract.ProjectView)
def update_retention(identifier: UUID, body: RetentionInput, request: Request, db: DB, actor: Actor):
    require(actor, "admin")
    project = project_scope(db, actor, str(identifier))
    project.retention_days = body.retention_days
    audit(
        db,
        actor.organization_id,
        actor.subject,
        "project.retention_changed",
        project.id,
        request.state.request_id,
        project_id=project.id,
    )
    commit(db)
    return serialize(project)
