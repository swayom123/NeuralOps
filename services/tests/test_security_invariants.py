import time
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from sqlalchemy import select, text, update
from sqlalchemy.exc import IntegrityError
from test_vertical_slice import batch, drain, ingest

from neuralops.config import Settings
from neuralops.db import SessionLocal, audit
from neuralops.maintenance import retain_project
from neuralops.models import (
    AuditEvent,
    Credential,
    Dataset,
    Job,
    Project,
    RateBucket,
    RuleVersion,
    Span,
    Trace,
)
from neuralops.worker import tick


def test_database_rejects_cross_tenant_writes_and_mutation_of_immutable_records(identity):
    alice, project_a, org_a, _ = identity()
    _, project_b, _, _ = identity()
    with pytest.raises(IntegrityError), SessionLocal.begin() as db:
        db.add(
            Span(
                organization_id=org_a,
                project_id=project_b,
                trace_id=uuid4().hex,
                span_id="a" * 16,
                parent_span_id="",
                operation="forbidden",
                service="forbidden",
                start_ns=time.time_ns(),
                end_ns=0,
                status="unset",
                attributes={},
            )
        )
    with SessionLocal.begin() as db:
        audit(db, org_a, "test", "test.immutable", "test")
    with pytest.raises(IntegrityError), SessionLocal.begin() as db:
        db.execute(update(AuditEvent).where(AuditEvent.organization_id == org_a).values(action="tampered"))
    dataset = alice.post(
        f"/v1/datasets?project_id={project_a}",
        json={
            "name": "Immutable fixture",
            "cases": [{"id": "case", "expected": "yes", "baseline_output": "no", "candidate_output": "yes"}],
        },
    ).json()
    with pytest.raises(IntegrityError), SessionLocal.begin() as db:
        db.execute(update(Dataset).where(Dataset.id == dataset["id"]).values(cases=[]))
    with SessionLocal() as db:
        assert len(db.get(Dataset, dataset["id"]).cases) == 1


def test_rule_snapshots_are_immutable_and_incremented(identity):
    client, project, _, _ = identity()
    rule = client.post(
        f"/v1/rules?project_id={project}",
        json={"name": "Versioned rule", "metric": "error_rate", "threshold": 10},
    ).json()
    assert (
        client.patch(f"/v1/rules/{rule['id']}?project_id={project}", json={"enabled": False}).status_code
        == 200
    )
    versions = client.get(f"/v1/rules/{rule['id']}/versions?project_id={project}").json()["items"]
    assert [v["version"] for v in versions] == [1, 2]
    assert versions[0]["manifest"]["enabled"] is True and versions[1]["manifest"]["enabled"] is False
    with pytest.raises(IntegrityError), SessionLocal.begin() as db:
        db.execute(update(RuleVersion).where(RuleVersion.rule_id == rule["id"]).values(manifest={}))


def test_shared_rate_limit_and_ingest_backpressure(identity, gateway):
    client, project, org, _ = identity()
    credential = client.post(f"/v1/credentials?project_id={project}").json()
    with SessionLocal.begin() as db:
        key = db.get(Credential, credential["id"])
        key.rate_minute, key.rate_count = int(time.time() // 60), 120
    rejected = ingest(gateway, credential["secret"], batch())
    assert rejected.status_code == 429
    with SessionLocal() as db:
        assert not db.scalar(select(Span.id).where(Span.organization_id == org))
    from neuralops.security import consume_rate, digest

    consume_rate(f"security-test:{org}", 1)
    with pytest.raises(Exception) as exc:
        consume_rate(f"security-test:{org}", 1)
    assert exc.value.status_code == 429
    with SessionLocal() as db:
        assert db.get(RateBucket, (digest(f"security-test:{org}"), int(time.time() // 60))).count == 2


def test_concurrent_retry_is_idempotent_and_worker_claim_is_single_consumer(identity, gateway):
    client, project, org, _ = identity()
    key = client.post(f"/v1/credentials?project_id={project}").json()["secret"]
    data = batch()
    with ThreadPoolExecutor(max_workers=4) as pool:
        assert list(pool.map(lambda _: ingest(gateway, key, data).status_code, range(4))) == [200] * 4
    with SessionLocal() as db:
        assert len(db.scalars(select(Span).where(Span.organization_id == org)).all()) == 2
        assert len(db.scalars(select(Job).where(Job.organization_id == org, Job.kind == "trace")).all()) == 1
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda _: tick(), range(2)))
    for _ in range(100):
        with SessionLocal() as db:
            if db.scalar(
                select(Job.status).where(Job.organization_id == org, Job.kind == "trace")
            ) == "COMPLETED":
                break
        tick()
    with SessionLocal() as db:
        job = db.scalar(select(Job).where(Job.organization_id == org, Job.kind == "trace"))
        assert job.status == "COMPLETED" and job.attempts == 1


def test_out_of_order_orphan_then_root_becomes_eligible(identity, gateway):
    client, project, _, _ = identity()
    key = client.post(f"/v1/credentials?project_id={project}").json()["secret"]
    data = batch()
    spans = data["resourceSpans"][0]["scopeSpans"][0]["spans"]
    root, child = spans[0], spans[1]
    data["resourceSpans"][0]["scopeSpans"][0]["spans"] = [child]
    assert ingest(gateway, key, data).status_code == 200
    drain()
    assert client.get(f"/v1/metrics/summary?project_id={project}").json()["eligible_count"] == 0
    data["resourceSpans"][0]["scopeSpans"][0]["spans"] = [root]
    assert ingest(gateway, key, data).status_code == 200
    drain()
    assert client.get(f"/v1/metrics/summary?project_id={project}").json()["eligible_count"] == 1


def test_retention_preserves_expired_evidence_status(identity, gateway):
    client, project, org, _ = identity()
    key = client.post(f"/v1/credentials?project_id={project}").json()["secret"]
    data = batch()
    for span in data["resourceSpans"][0]["scopeSpans"][0]["spans"]:
        span["startTimeUnixNano"] = str(int(span["startTimeUnixNano"]) - 8 * 86400 * 10**9)
        span["endTimeUnixNano"] = str(int(span["endTimeUnixNano"]) - 8 * 86400 * 10**9)
    assert ingest(gateway, key, data).status_code == 200
    drain()
    trace_id = data["resourceSpans"][0]["scopeSpans"][0]["spans"][0]["traceId"]
    with SessionLocal.begin() as db:
        assert retain_project(db, db.get(Project, project)) == 1
    detail = client.get(f"/v1/traces/{trace_id}?project_id={project}")
    assert detail.status_code == 410 and detail.json()["code"] == "EVIDENCE_EXPIRED"
    with SessionLocal() as db:
        assert not db.scalar(select(Span.id).where(Span.organization_id == org))


def test_production_settings_fail_closed():
    common = {
        "database_url": "postgresql+psycopg://localhost/neuralops",
        "session_secret": "x" * 48,
        "environment": "production",
        "public_origin": "https://neuralops.example",
    }
    with pytest.raises(ValueError):
        Settings(**common, dev_auth=True)
    with pytest.raises(ValueError):
        Settings(**common, dev_auth=False, oidc_issuer="", oidc_client_id="", oidc_client_secret="")
    with pytest.raises(ValueError):
        Settings(**{**common, "public_origin": "http://neuralops.example"})


def test_invalid_nested_telemetry_is_redacted_or_rejected(identity, gateway):
    client, project, _, _ = identity()
    key = client.post(f"/v1/credentials?project_id={project}").json()["secret"]
    data = batch()
    spans = data["resourceSpans"][0]["scopeSpans"][0]["spans"]
    spans[0]["attributes"] += [
        {"key": "gen_ai.request.model", "value": {"stringValue": "Bearer should-never-persist"}},
        {
            "key": "arbitrary.nested",
            "value": {
                "kvlistValue": {"values": [{"key": "password", "value": {"stringValue": "nested-secret"}}]}
            },
        },
        {"key": "gen_ai.system", "value": {"stringValue": "customer@example.com"}},
    ]
    assert ingest(gateway, key, data).status_code == 200
    drain()
    detail = client.get(f"/v1/traces/{spans[0]['traceId']}?project_id={project}")
    assert all(
        value not in detail.text
        for value in ["should-never-persist", "nested-secret", "customer@example.com"]
    )
    assert detail.json()["spans"][0]["redacted_count"] >= 3
    data = batch()
    data["resourceSpans"][0]["scopeSpans"][0]["spans"][0]["status"] = {"code": "STATUS_CODE_ERROR"}
    assert ingest(gateway, key, data).status_code == 400
    assert (
        gateway.post(
            "/v1/traces", content=b"compressed-data", headers={"Content-Encoding": "gzip"}
        ).status_code
        == 415
    )


def test_postgres_row_security_denies_unscoped_and_other_tenant_reads(identity, gateway):
    alice, project_a, org_a, _ = identity()
    bob, project_b, _, _ = identity()
    for client, project in [(alice, project_a), (bob, project_b)]:
        key = client.post(f"/v1/credentials?project_id={project}").json()["secret"]
        assert ingest(gateway, key, batch()).status_code == 200
    drain()
    with SessionLocal.begin() as db:
        db.execute(text("SET LOCAL ROLE neuralops_api"))
        assert db.scalars(select(Trace)).all() == []  # Missing tenant context denies every row.
        from neuralops.db import set_tenant

        set_tenant(db, org_a)
        rows = db.scalars(select(Trace)).all()
        assert len(rows) == 1 and rows[0].project_id == project_a
        assert db.scalars(select(Trace).where(Trace.project_id == project_b)).all() == []


def test_project_limited_operator_cannot_read_other_project_audit(identity):
    admin, project_a, org, _ = identity()
    operator, project_b, _, _ = identity("operator", organization_id=org)
    assert admin.post(f"/v1/credentials?project_id={project_a}").status_code == 201
    assert (
        operator.post(
            f"/v1/rules?project_id={project_b}",
            json={"name": "Scoped audit fixture", "metric": "error_rate", "threshold": 10},
        ).status_code
        == 201
    )
    assert operator.get("/v1/audit").status_code == 422
    assert operator.get(f"/v1/audit?project_id={project_a}").status_code == 404
    visible = operator.get(f"/v1/audit?project_id={project_b}").json()["items"]
    assert {event["action"] for event in visible} == {"rule.created"}
    assert all(event["project_id"] == project_b for event in visible)


def test_runtime_roles_support_actual_api_ingest_and_worker_flow(identity, gateway, monkeypatch):
    from sqlalchemy import event
    from sqlalchemy.orm import Session, sessionmaker

    from neuralops import api as api_module
    from neuralops import telemetry, worker
    from neuralops.db import database, engine

    client, project, _, _ = identity()

    def apply_role(session, transaction, connection):
        role = session.info.get("runtime_role")
        if role:
            # Constant role names supplied only by this test, never user input.
            connection.execute(text(f"SET LOCAL ROLE {role}"))

    event.listen(Session, "after_begin", apply_role)
    api_factory = sessionmaker(bind=engine, expire_on_commit=False, info={"runtime_role": "neuralops_api"})
    ingest_factory = sessionmaker(
        bind=engine, expire_on_commit=False, info={"runtime_role": "neuralops_ingest"}
    )
    worker_factory = sessionmaker(
        bind=engine, expire_on_commit=False, info={"runtime_role": "neuralops_worker"}
    )

    def role_database():
        with api_factory() as db:
            yield db

    api_module.app.dependency_overrides[database] = role_database
    monkeypatch.setattr(telemetry, "SessionLocal", ingest_factory)
    monkeypatch.setattr(worker, "SessionLocal", worker_factory)
    try:
        credential = client.post(f"/v1/credentials?project_id={project}")
        assert credential.status_code == 201, credential.text
        assert (
            client.post(
                f"/v1/rules?project_id={project}",
                json={
                    "name": "Least privilege fixture",
                    "metric": "error_rate",
                    "threshold": 10,
                    "min_samples": 1,
                },
            ).status_code
            == 201
        )
        assert ingest(gateway, credential.json()["secret"], batch()).status_code == 200
        drain()
        summary = client.get(f"/v1/metrics/summary?project_id={project}")
        assert summary.status_code == 200, summary.text
        assert summary.json()["executions"] == 1 and summary.json()["active_incidents"] == 1
        assert client.get("/v1/audit").status_code == 200
        cases = [{"id": "case", "expected": "ok", "baseline_output": "bad", "candidate_output": "ok"}]
        dataset = client.post(f"/v1/datasets?project_id={project}", json={"name": "Role fixture", "cases": cases})
        assert dataset.status_code == 201, dataset.text
        version = client.post(f"/v1/datasets/{dataset.json()['id']}/versions?project_id={project}",
                              json={"cases": cases})
        assert version.status_code == 201, version.text
        assert version.json()["version"] == 2
        run = client.post(f"/v1/evaluations?project_id={project}",
                          json={"dataset_id": version.json()["id"], "baseline": "v1", "candidate": "v2"},
                          headers={"Idempotency-Key": str(uuid4())})
        assert run.status_code == 202, run.text
        drain()
        report = client.get(f"/v1/evaluations/{run.json()['id']}/export?project_id={project}")
        assert report.status_code == 200, report.text
        assert report.json()["dataset_version"] == 2
    finally:
        api_module.app.dependency_overrides.clear()
        event.remove(Session, "after_begin", apply_role)


def test_approval_manifest_expiry_and_disabled_executor_invariants(identity, gateway):
    client, project, org, _ = identity()
    key = client.post(f"/v1/credentials?project_id={project}").json()["secret"]
    client.post(
        f"/v1/rules?project_id={project}",
        json={"name": "Recovery policy fixture", "metric": "error_rate", "threshold": 1, "min_samples": 1},
    )
    ingest(gateway, key, batch())
    drain()
    incident = client.get(f"/v1/incidents?project_id={project}").json()["items"][0]
    proposal = client.post(
        f"/v1/remediations?project_id={project}",
        json={
            "incident_id": incident["id"],
            "action": "restart_service",
            "target": "staging/fixture",
            "rollback_plan": "Restore known healthy fixture configuration.",
        },
        headers={"Idempotency-Key": "guarded-proposal-key"},
    ).json()
    approver, _, _, _ = identity("approver", organization_id=org, project_id=project)
    executor, _, _, _ = identity("executor", organization_id=org, project_id=project)
    assert (
        approver.post(
            f"/v1/remediations/{proposal['id']}/approve?project_id={project}",
            json={"manifest_hash": "f" * 64},
        ).status_code
        == 409
    )
    from neuralops.models import Remediation

    with SessionLocal.begin() as db:
        # Simulated validation state for a negative executor-boundary test, not a real target validation.
        db.get(Remediation, proposal["id"]).state = "VALIDATED"
    assert (
        approver.post(
            f"/v1/remediations/{proposal['id']}/approve?project_id={project}",
            json={"manifest_hash": proposal["manifest_hash"]},
        ).status_code
        == 503
    )
    assert executor.post(f"/v1/remediations/{proposal['id']}/execute?project_id={project}").status_code == 503
    with SessionLocal() as db:
        row = db.get(Remediation, proposal["id"])
        assert row.approver is None and row.state == "VALIDATED"
    with pytest.raises(IntegrityError), SessionLocal.begin() as db:
        db.get(Remediation, proposal["id"]).manifest = {"action": "arbitrary_shell"}
