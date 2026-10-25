"""Bounded OTLP decoding and metadata-only normalization; no producer scope is trusted."""

import json
import re
import time
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import FastAPI, Header, Request
from google.protobuf.json_format import MessageToDict
from google.protobuf.message import DecodeError
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
    ExportTraceServiceRequest,
    ExportTraceServiceResponse,
)
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert
from starlette.concurrency import run_in_threadpool
from starlette.responses import Response

from .db import SessionLocal, ensure_runtime_role, set_tenant
from .http import configure
from .models import Credential, Job, Project, Span, now
from .security import consume_rate, digest, fail


@asynccontextmanager
async def lifespan(app: FastAPI):
    await run_in_threadpool(ensure_runtime_role, "neuralops_ingest")
    yield


app = FastAPI(
    lifespan=lifespan, title="NeuralOps OTLP Gateway", docs_url=None, redoc_url=None, openapi_url=None
)
configure(app)
ID32 = re.compile(r"^[0-9a-fA-F]{32}$")
ID16 = re.compile(r"^[0-9a-fA-F]{16}$")
SAFE_NAME = re.compile(r"^[\w .:/@-]{1,128}$")
SECRET = re.compile(
    r"(?i)(bearer\s|sk[-_]|api[-_]?key|password|secret|eyJ[a-zA-Z0-9_-]+\.|[\w.+-]+@[\w.-]+\.[a-z]{2,})"
)
ALLOWED_STRINGS = {
    "service.name",
    "service.version",
    "gen_ai.system",
    "gen_ai.provider.name",
    "gen_ai.request.model",
    "gen_ai.response.model",
    "gen_ai.operation.name",
    "gen_ai.tool.name",
    "error.type",
    "deployment.environment.name",
}
ALLOWED_NUMBERS = {
    "gen_ai.usage.input_tokens",
    "gen_ai.usage.output_tokens",
    "http.response.status_code",
}


class OtlpModel(BaseModel):
    model_config = ConfigDict(extra="ignore")


class Attribute(OtlpModel):
    key: str = Field(max_length=256)
    value: dict


class SpanInput(OtlpModel):
    traceId: str
    spanId: str
    parentSpanId: str = ""
    name: str = Field(max_length=1024)
    startTimeUnixNano: str | int
    endTimeUnixNano: str | int = "0"
    attributes: list[Attribute] = Field(default_factory=list, max_length=64)
    status: dict = Field(default_factory=dict)
    events: list[dict] = Field(default_factory=list, max_length=128)
    links: list[dict] = Field(default_factory=list, max_length=32)


class ScopeSpans(OtlpModel):
    spans: list[SpanInput] = Field(default_factory=list, max_length=500)


class Resource(OtlpModel):
    attributes: list[Attribute] = Field(default_factory=list, max_length=64)


class ResourceSpans(OtlpModel):
    resource: Resource = Field(default_factory=Resource)
    scopeSpans: list[ScopeSpans] = Field(default_factory=list, max_length=32)


class Batch(OtlpModel):
    resourceSpans: list[ResourceSpans] = Field(default_factory=list, max_length=32)


def safe_name(value: str) -> str:
    return value if SAFE_NAME.fullmatch(value) and not SECRET.search(value) else "[redacted]"


def metadata(attributes: list[Attribute]) -> tuple[dict, int]:
    result, dropped = {}, 0
    for attr in attributes:
        if attr.key in ALLOWED_STRINGS:
            value = attr.value.get("stringValue")
            if isinstance(value, str) and value and safe_name(value) == value:
                result[attr.key] = value
                continue
        elif attr.key in ALLOWED_NUMBERS:
            value = attr.value.get("intValue")
            if isinstance(value, (str, int)) and not isinstance(value, bool):
                try:
                    number = int(value)
                    if 0 <= number <= 1_000_000_000:
                        result[attr.key] = number
                        continue
                except (ValueError, OverflowError):
                    pass
        dropped += 1
    return result, dropped


def validate_id(value: str, pattern: re.Pattern) -> str:
    if not isinstance(value, str) or not pattern.fullmatch(value) or set(value) == {"0"}:
        fail(400, "INVALID_OTLP", "Invalid trace or span identifier.")
    return value.lower()


def normalize(batch: Batch, credential: Credential) -> list[dict]:
    result = []
    for resource in batch.resourceSpans:
        res, res_dropped = metadata(resource.resource.attributes)
        for scope in resource.scopeSpans:
            for span in scope.spans:
                if len(result) >= 500:
                    fail(413, "BATCH_TOO_LARGE", "At most 500 spans per request.")
                attributes, dropped = metadata(span.attributes)
                attributes = {**res, **attributes}
                try:
                    start, end = int(span.startTimeUnixNano), int(span.endTimeUnixNano)
                except (ValueError, OverflowError):
                    fail(400, "INVALID_OTLP", "Invalid timestamps.")
                if not (0 < start < 4_102_444_800_000_000_000) or (
                    end and not start <= end < 4_102_444_800_000_000_000
                ):
                    fail(400, "INVALID_OTLP", "Invalid timestamp interval.")
                code = span.status.get("code", 0)
                if type(code) is not int or code not in {0, 1, 2}:
                    fail(
                        400,
                        "INVALID_OTLP",
                        "Status must use OTLP integer enum encoding.",
                    )
                links = []
                for link in span.links:
                    links.append(
                        {
                            "trace_id": validate_id(link.get("traceId", ""), ID32),
                            "span_id": validate_id(link.get("spanId", ""), ID16),
                        }
                    )
                result.append(
                    {
                        "organization_id": credential.organization_id,
                        "project_id": credential.project_id,
                        "trace_id": validate_id(span.traceId, ID32),
                        "span_id": validate_id(span.spanId, ID16),
                        "parent_span_id": validate_id(span.parentSpanId, ID16) if span.parentSpanId else "",
                        "operation": safe_name(span.name),
                        "service": attributes.get("service.name", "unknown-service"),
                        "start_ns": start,
                        "end_ns": end,
                        "status": "error" if code == 2 else "ok" if code == 1 else "unset",
                        "attributes": attributes,
                        "links": links,
                        "redacted_count": dropped + res_dropped + len(span.events),
                    }
                )
    if not result:
        fail(400, "EMPTY_BATCH", "Provide at least one span.")
    return result


def decode(body: bytes, content_type: str) -> Batch:
    try:
        if content_type == "application/x-protobuf":
            message = ExportTraceServiceRequest()
            message.ParseFromString(body)
            data = MessageToDict(message)
            # Protobuf JSON maps bytes to base64; OTLP JSON specifically requires hex IDs.
            for resource, raw_res in zip(data.get("resourceSpans", []), message.resource_spans):
                for scope, raw_scope in zip(resource.get("scopeSpans", []), raw_res.scope_spans):
                    for span, raw in zip(scope.get("spans", []), raw_scope.spans):
                        span.update(
                            traceId=raw.trace_id.hex(),
                            spanId=raw.span_id.hex(),
                            parentSpanId=raw.parent_span_id.hex(),
                        )
                        if raw.HasField("status"):
                            span["status"] = {"code": raw.status.code}
                        for link, raw_link in zip(span.get("links", []), raw.links):
                            link.update(
                                traceId=raw_link.trace_id.hex(),
                                spanId=raw_link.span_id.hex(),
                            )
            return Batch.model_validate(data)
        if content_type == "application/json":
            return Batch.model_validate_json(body)
        fail(415, "UNSUPPORTED_MEDIA_TYPE", "Use OTLP JSON or protobuf.")
    except (ValidationError, DecodeError, ValueError, RecursionError, TypeError):
        fail(400, "INVALID_OTLP", "Malformed or out-of-bounds OTLP payload.")


@app.get("/health/live")
def live():
    return {"status": "alive"}


@app.post("/v1/traces")
async def ingest(request: Request, authorization: Annotated[str | None, Header()] = None):
    if not authorization or not authorization.startswith("Bearer ") or len(authorization) > 256:
        fail(401, "INVALID_CREDENTIAL", "Valid ingestion credential required.")
    body = await request.body()
    content_type = request.headers.get("content-type", "").split(";")[0]
    await run_in_threadpool(persist, body, content_type, authorization)
    if content_type == "application/x-protobuf":
        return Response(
            ExportTraceServiceResponse().SerializeToString(),
            media_type="application/x-protobuf",
        )
    return Response(json.dumps({}), media_type="application/json")


def persist(body: bytes, content_type: str, authorization: str):
    # Rate attempts using a committed shared bucket, including malformed authenticated requests.
    with SessionLocal() as db:
        credential = db.scalar(select(Credential).where(Credential.verifier == digest(authorization[7:])))
        if not credential or credential.revoked or credential.expires_at <= now():
            fail(401, "INVALID_CREDENTIAL", "Credential is invalid, expired or revoked.")
        consume_rate(f"ingest:{credential.id}", 120, db=db)
    with SessionLocal.begin() as db:
        # Recheck under lock: revocation between the attempt quota and persistence must take effect.
        credential = db.scalar(
            select(Credential).where(Credential.verifier == digest(authorization[7:])).with_for_update()
        )
        if not credential or credential.revoked or credential.expires_at <= now():
            fail(401, "INVALID_CREDENTIAL", "Credential is invalid, expired or revoked.")
        set_tenant(db, credential.organization_id)
        db.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:scope, 0))"),
            {"scope": f"{credential.organization_id}:{credential.project_id}"},
        )
        project = db.scalar(select(Project).where(Project.id == credential.project_id))
        minute = int(time.time() // 60)
        count = credential.rate_count if credential.rate_minute == minute else 0
        if count >= 120:
            fail(429, "RATE_LIMITED", "Ingestion quota exceeded. Retry next minute.")
        rows = normalize(decode(body, content_type), credential)
        credential.rate_minute, credential.rate_count = minute, count + 1
        added = 0
        for trace_id in {row["trace_id"] for row in rows}:
            existing = set(
                db.scalars(
                    select(Span.span_id).where(
                        Span.organization_id == credential.organization_id,
                        Span.project_id == project.id,
                        Span.trace_id == trace_id,
                    )
                )
            )
            incoming = {row["span_id"] for row in rows if row["trace_id"] == trace_id}
            if len(existing | incoming) > 2000:
                fail(413, "TRACE_TOO_LARGE", "At most 2,000 spans per trace.")
            added += len(incoming - existing)
        stored = db.scalar(
            select(func.count())
            .select_from(Span)
            .where(Span.organization_id == credential.organization_id, Span.project_id == project.id)
        )
        if stored + added > 100_000:
            fail(429, "STORAGE_QUOTA", "Project telemetry quota reached.")
        changed = set()
        for row in rows:
            row["attributes"]["deployment.environment.name"] = project.environment
            statement = insert(Span).values(**row)
            changed_id = db.scalar(
                statement.on_conflict_do_update(
                    index_elements=["organization_id", "project_id", "trace_id", "span_id"],
                    set_={
                        key: getattr(statement.excluded, key)
                        for key in ["end_ns", "status", "attributes", "links", "redacted_count"]
                    },
                    where=(Span.end_ns == 0)
                    & (statement.excluded.end_ns > 0)
                    & (Span.start_ns == statement.excluded.start_ns),
                ).returning(Span.id)
            )
            if changed_id:
                changed.add(row["trace_id"])
        pending = db.scalar(
            select(func.count())
            .select_from(Job)
            .where(
                Job.organization_id == credential.organization_id,
                Job.project_id == project.id,
                Job.status.in_(["QUEUED", "RUNNING"]),
            )
        )
        if changed and pending + len(changed) > 1000:
            fail(429, "QUEUE_SATURATED", "Processing backlog reached its bound. Retry with backoff.")
        for trace_id in sorted(changed):
            db.add(
                Job(
                    organization_id=credential.organization_id,
                    project_id=project.id,
                    kind="trace",
                    resource_id=trace_id,
                )
            )
