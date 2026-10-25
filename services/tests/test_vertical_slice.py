import time
from datetime import timedelta
from uuid import uuid4

from fastapi.testclient import TestClient
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest
from sqlalchemy import func, select

from neuralops.api import app
from neuralops.db import SessionLocal
from neuralops.models import Credential, EvidenceLink, Hypothesis, Job, Membership, Span, UserSession, now
from neuralops.worker import tick


def payload(error=True, trace_id=None):
    # Actual synthetic fixture encoding, timestamps obtained from a real clock.
    start = time.time_ns() - 20_000_000
    return {
        "resourceSpans": [
            {
                "resource": {
                    "attributes": [
                        {"key": "service.name", "value": {"stringValue": "synthetic-fixture-rag"}},
                        {"key": "organization_id", "value": {"stringValue": "attacker-tenant"}},
                        {"key": "authorization", "value": {"stringValue": "Bearer secret-must-disappear"}},
                    ]
                },
                "scopeSpans": [
                    {
                        "spans": [
                            {
                                "traceId": trace_id or uuid4().hex,
                                "spanId": "a" * 16,
                                "name": "synthetic-fixture/request",
                                "startTimeUnixNano": str(start),
                                "endTimeUnixNano": str(start + 18_000_000),
                                "status": {"code": 1},
                                "attributes": [
                                    {"key": "gen_ai.usage.input_tokens", "value": {"intValue": "12"}},
                                    {"key": "gen_ai.usage.output_tokens", "value": {"intValue": "8"}},
                                    {
                                        "key": "gen_ai.prompt",
                                        "value": {"stringValue": "private customer prompt"},
                                    },
                                ],
                            },
                            {
                                "traceId": trace_id or "",
                                "spanId": "b" * 16,
                                "parentSpanId": "a" * 16,
                                "name": "synthetic-fixture/retrieve",
                                "startTimeUnixNano": str(start + 1_000_000),
                                "endTimeUnixNano": str(start + 14_000_000),
                                "status": {"code": 2 if error else 1},
                                "attributes": [
                                    {"key": "error.type", "value": {"stringValue": "TimeoutError"}}
                                ],
                                "events": [
                                    {
                                        "name": "exception",
                                        "attributes": [
                                            {"key": "exception.message", "value": {"stringValue": "secret"}}
                                        ],
                                    }
                                ],
                            },
                        ]
                    }
                ],
            }
        ]
    }


def batch(error=True):
    data = payload(error, uuid4().hex)
    return data


def ingest(gateway, key, data):
    return gateway.post("/v1/traces", json=data, headers={"Authorization": f"Bearer {key}"})


def drain():
    for _ in range(1000):
        if not tick():
            return
    raise AssertionError("Worker did not drain")


def test_complete_vertical_slice(identity, gateway):
    client, project, org, _ = identity()
    key_response = client.post(f"/v1/credentials?project_id={project}")
    assert key_response.status_code == 201, key_response.text
    key = key_response.json()["secret"]
    key_list = client.get(f"/v1/credentials?project_id={project}").json()
    assert key not in str(key_list) and "verifier" not in str(key_list)
    rule = client.post(
        f"/v1/rules?project_id={project}",
        json={
            "name": "Synthetic fixture failure",
            "metric": "error_rate",
            "threshold": 10,
            "min_samples": 2,
            "window_minutes": 15,
            "cooldown_minutes": 30,
            "severity": "high",
        },
    )
    assert rule.status_code == 201, rule.text
    data1, data2 = batch(), batch(False)
    assert ingest(gateway, key, data1).status_code == 200
    assert ingest(gateway, key, data1).status_code == 200  # Idempotent spans, retryable jobs.
    drain()
    assert client.get(f"/v1/incidents?project_id={project}").json()["items"] == []  # Min-sample guard.
    assert ingest(gateway, key, data2).status_code == 200
    drain()
    summary = client.get(f"/v1/metrics/summary?project_id={project}").json()
    assert summary["executions"] == 2 and summary["success_rate"] == 50
    assert summary["p95_ms"] == 18 and summary["tokens"] == 40 and summary["estimated_cost"] is None
    assert sum(p["sample_count"] for p in summary["series"]) == 2
    detail = client.get(
        f"/v1/traces/{data1['resourceSpans'][0]['scopeSpans'][0]['spans'][0]['traceId']}?project_id={project}"
    )
    assert detail.status_code == 200
    assert (
        detail.json()["span_count"] == 2 and detail.json()["duration_ms"] == 18
    )  # Parallel/child duration never summed.
    assert "private customer prompt" not in detail.text and "secret-must-disappear" not in detail.text
    with SessionLocal() as db:
        stored = db.scalars(select(Span).where(Span.organization_id == org)).all()
        assert len(stored) == 4 and all(
            "authorization" not in s.attributes and "gen_ai.prompt" not in s.attributes for s in stored
        )
    incidents = client.get(f"/v1/incidents?project_id={project}").json()["items"]
    assert len(incidents) == 1
    incident = incidents[0]
    hypotheses = client.get(f"/v1/incidents/{incident['id']}/hypotheses?project_id={project}").json()
    assert hypotheses["items"][0]["evidence_class"] == "partial"
    assert (
        hypotheses["items"][0]["supporting"]
        and hypotheses["items"][0]["counterevidence"]
        and hypotheses["items"][0]["missing"]
    )
    with SessionLocal() as db:
        persisted = db.scalar(select(Hypothesis).where(Hypothesis.incident_id == incident["id"]))
        assert persisted and db.scalar(
            select(EvidenceLink).where(EvidenceLink.hypothesis_id == persisted.id)
        )
    assert (
        client.patch(
            f"/v1/incidents/{incident['id']}?project_id={project}", json={"status": "ACKNOWLEDGED"}
        ).status_code
        == 200
    )
    # Redelivered telemetry updates grouped evidence, never creates a second incident.
    assert ingest(gateway, key, data1).status_code == 200
    drain()
    assert len(client.get(f"/v1/incidents?project_id={project}").json()["items"]) == 1
    assert (
        client.patch(
            f"/v1/incidents/{incident['id']}?project_id={project}", json={"status": "RESOLVED"}
        ).status_code
        == 200
    )
    assert client.get(f"/v1/metrics/summary?project_id={project}").json()["active_incidents"] == 0
    dataset = client.post(
        f"/v1/datasets?project_id={project}",
        json={
            "name": "Paired replay fixture",
            "cases": [
                {"id": f"case-{i}", "expected": "yes", "baseline_output": "no", "candidate_output": "yes"}
                for i in range(40)
            ],
        },
    )
    assert dataset.status_code == 201, dataset.text
    run_body = {"dataset_id": dataset.json()["id"], "baseline": "recorded-v1", "candidate": "recorded-v2"}
    run = client.post(
        f"/v1/evaluations?project_id={project}", json=run_body, headers={"Idempotency-Key": "test-replay-key"}
    )
    assert run.status_code == 202, run.text
    repeated = client.post(
        f"/v1/evaluations?project_id={project}", json=run_body, headers={"Idempotency-Key": "test-replay-key"}
    )
    assert repeated.json()["id"] == run.json()["id"]
    conflict = client.post(
        f"/v1/evaluations?project_id={project}",
        json={**run_body, "candidate": "changed"},
        headers={"Idempotency-Key": "test-replay-key"},
    )
    assert conflict.status_code == 409
    drain()
    result = client.get(f"/v1/evaluations/{run.json()['id']}?project_id={project}").json()
    assert (
        result["status"] == "COMPLETED"
        and result["decision"] == "PASS"
        and result["results"]["candidate_score"] == 1
    )
    assert len(result["results"]["cases"]) == 40
    proposal_body = {
        "incident_id": incident["id"],
        "action": "restart_service",
        "target": "staging/synthetic-fixture",
        "rollback_plan": "Restore prior test deployment.",
        "expires_minutes": 30,
    }
    proposal = client.post(
        f"/v1/remediations?project_id={project}",
        json=proposal_body,
        headers={"Idempotency-Key": "test-proposal-key"},
    )
    assert proposal.status_code == 201, proposal.text
    proposal_id = proposal.json()["id"]
    assert client.post(f"/v1/remediations/{proposal_id}/execute?project_id={project}").status_code == 403
    assert (
        client.post(
            f"/v1/remediations/{proposal_id}/approve?project_id={project}",
            json={"manifest_hash": proposal.json()["manifest_hash"]},
        ).status_code
        == 403
    )
    assert (
        client.post(f"/v1/remediations/{proposal_id}/reject?project_id={project}").json()["state"]
        == "REJECTED"
    )
    assert (
        client.post(f"/v1/remediations/{proposal_id}/reject?project_id={project}").json()["state"]
        == "REJECTED"
    )
    audit = client.get("/v1/audit?limit=100").json()["items"]
    assert {
        "credential.created",
        "incident.created",
        "diagnosis.completed",
        "evaluation.queued",
        "evaluation.completed",
        "remediation.proposed",
        "remediation.rejected",
    } <= {a["action"] for a in audit}
    assert key not in str(audit)
    assert (
        client.delete(f"/v1/credentials/{key_response.json()['id']}?project_id={project}").status_code == 200
    )
    assert ingest(gateway, key, batch()).status_code == 401


def test_auth_csrf_logout_revocation_and_live_role_changes(identity):
    anonymous = TestClient(app)
    assert anonymous.get("/v1/projects").status_code == 401
    client, project, _, member_id = identity()
    assert (
        client.post(
            "/v1/projects", headers={"X-CSRF-Token": ""}, json={"name": "Denied", "slug": "denied"}
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/v1/projects",
            headers={"Origin": "https://evil.example"},
            json={"name": "Denied", "slug": "denied"},
        ).status_code
        == 403
    )
    with SessionLocal.begin() as db:
        db.get(Membership, member_id).role = "viewer"
    assert client.post(f"/v1/credentials?project_id={project}").status_code == 403
    assert client.get(f"/v1/traces?project_id={project}").status_code == 200
    assert client.post("/v1/auth/logout").status_code == 200
    assert client.get("/v1/me").status_code == 401
    client, _, _, member_id = identity()
    with SessionLocal.begin() as db:
        session = db.scalar(select(UserSession).where(UserSession.membership_id == member_id))
        session.expires_at = now() - timedelta(seconds=1)
    assert client.get("/v1/me").status_code == 401


def test_tenant_and_project_isolation_every_resource(identity, gateway):
    alice, project_a, org_a, _ = identity()
    bob, project_b, _, _ = identity()
    restricted, _, _, _ = identity("viewer", organization_id=org_a, project_id=project_a, project_ids=[])
    for client, project in [(bob, project_a), (alice, project_b), (restricted, project_a)]:
        for endpoint in [
            "traces",
            "metrics/summary",
            "services",
            "analytics",
            "rules",
            "incidents",
            "datasets",
            "evaluations",
            "remediations",
        ]:
            assert client.get(f"/v1/{endpoint}?project_id={project}").status_code == 404, endpoint
    assert restricted.get("/v1/projects").json()["items"] == []
    key = alice.post(f"/v1/credentials?project_id={project_a}").json()["secret"]
    data = batch()
    assert ingest(gateway, key, data).status_code == 200
    drain()
    trace = data["resourceSpans"][0]["scopeSpans"][0]["spans"][0]["traceId"]
    assert bob.get(f"/v1/traces/{trace}?project_id={project_b}").status_code == 404
    assert bob.get(f"/v1/traces/{trace}?project_id={project_a}").status_code == 404
    with SessionLocal() as db:
        assert (
            db.scalar(
                select(func.count())
                .select_from(Span)
                .where(Span.organization_id == org_a, Span.trace_id == trace)
            )
            == 2
        )
    # Ingestion bearer credentials cannot impersonate browser sessions.
    assert TestClient(app).get("/v1/projects", headers={"Authorization": f"Bearer {key}"}).status_code == 401


def test_ingestion_rejects_invalid_expired_and_oversized_payloads(identity, gateway):
    client, project, _, _ = identity()
    response = client.post(f"/v1/credentials?project_id={project}").json()
    key = response["secret"]
    assert ingest(gateway, "invalid", batch()).status_code == 401
    assert (
        gateway.post(
            "/v1/traces",
            content="{" * 200,
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
        ).status_code
        == 400
    )
    assert (
        gateway.post(
            "/v1/traces",
            content=b"\xff\xff",
            headers={"Content-Type": "application/x-protobuf", "Authorization": f"Bearer {key}"},
        ).status_code
        == 400
    )
    assert gateway.post("/v1/traces", content=b"x" * 1_048_577).status_code == 413
    data = batch()
    data["resourceSpans"][0]["scopeSpans"][0]["spans"][0]["traceId"] = "0" * 32
    assert ingest(gateway, key, data).status_code == 400
    with SessionLocal.begin() as db:
        db.get(Credential, response["id"]).expires_at = now() - timedelta(seconds=1)
    assert ingest(gateway, key, batch()).status_code == 401


def test_binary_protobuf_and_token_missingness(identity, gateway):
    client, project, _, _ = identity()
    key = client.post(f"/v1/credentials?project_id={project}").json()["secret"]
    message = ExportTraceServiceRequest()
    span = message.resource_spans.add().scope_spans.add().spans.add()
    span.trace_id, span.span_id = uuid4().bytes, b"12345678"
    span.name = "synthetic-fixture/protobuf"
    span.start_time_unix_nano, span.end_time_unix_nano = time.time_ns() - 10_000_000, time.time_ns()
    span.status.code = 1
    response = gateway.post(
        "/v1/traces",
        content=message.SerializeToString(),
        headers={"Content-Type": "application/x-protobuf", "Authorization": f"Bearer {key}"},
    )
    assert response.status_code == 200 and response.headers["content-type"] == "application/x-protobuf"
    drain()
    summary = client.get(f"/v1/metrics/summary?project_id={project}").json()
    assert (
        summary["tokens"] is None and summary["token_trace_coverage"] == 0 and summary["success_rate"] == 100
    )


def test_incomplete_and_cycles_are_excluded_from_eligible_metrics(identity, gateway):
    client, project, _, _ = identity()
    key = client.post(f"/v1/credentials?project_id={project}").json()["secret"]
    data = batch()
    spans = data["resourceSpans"][0]["scopeSpans"][0]["spans"]
    spans[0]["parentSpanId"] = spans[1]["spanId"]
    assert ingest(gateway, key, data).status_code == 200
    drain()
    summary = client.get(f"/v1/metrics/summary?project_id={project}").json()
    assert summary["eligible_count"] == 0 and summary["success_rate"] is None and summary["p95_ms"] is None
    detail = client.get(f"/v1/traces/{spans[0]['traceId']}?project_id={project}").json()
    assert "cycle" in detail["issues"] and "missing_root" in detail["issues"]


def test_viewer_writes_invalid_filters_and_fail_closed_executor(identity):
    viewer, project, _, _ = identity("viewer")
    assert (
        viewer.post(
            f"/v1/rules?project_id={project}",
            json={"name": "Denied rule", "metric": "error_rate", "threshold": 1},
        ).status_code
        == 403
    )
    assert viewer.get("/v1/audit").status_code == 403
    assert viewer.get(f"/v1/traces?project_id={project}&hours=9999").status_code == 422
    assert viewer.get(f"/v1/traces?project_id={project}&status=arbitrary").status_code == 422
    assert (
        viewer.get(f"/v1/traces?project_id={project}&search=%27%3B%20DROP%20TABLE%20spans%3B--").status_code
        == 200
    )
    assert viewer.post(f"/v1/remediations/{uuid4()}/execute?project_id={project}").status_code == 403


def test_sparse_evaluation_inconclusive_and_dead_letter(identity):
    client, project, org, _ = identity()
    dataset = client.post(
        f"/v1/datasets?project_id={project}",
        json={
            "name": "Sparse fixture",
            "cases": [{"id": "1", "expected": "yes", "baseline_output": "no", "candidate_output": "yes"}],
        },
    ).json()
    run = client.post(
        f"/v1/evaluations?project_id={project}",
        json={"dataset_id": dataset["id"], "baseline": "v1", "candidate": "v2"},
        headers={"Idempotency-Key": "sparse-replay-key"},
    ).json()
    drain()
    assert (
        client.get(f"/v1/evaluations/{run['id']}?project_id={project}").json()["decision"] == "INCONCLUSIVE"
    )
    with SessionLocal.begin() as db:
        job = Job(organization_id=org, project_id=project, kind="unknown", resource_id="invalid", attempts=4)
        db.add(job)
        db.flush()
        identifier = job.id
    tick()
    with SessionLocal() as db:
        job = db.get(Job, identifier)
        assert job.status == "DEAD_LETTER" and job.attempts == 5 and job.last_error == "PROCESSING_FAILED"
