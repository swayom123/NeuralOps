from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4

from sqlalchemy import func, select
from test_vertical_slice import drain

from neuralops.db import SessionLocal
from neuralops.domain import critical_path, detection_result
from neuralops.models import Detection, SLOSnapshot, Trace, now
from neuralops.worker import tick


def measured_trace(value: float, status: str = "ok", offset: int = 0):
    return SimpleNamespace(
        id=f"trace-{offset:03d}",
        trace_id=f"{offset:032x}",
        start_ns=offset,
        duration_ms=value,
        status=status,
    )


def detector(kind: str, metric: str = "p95_latency_ms"):
    return SimpleNamespace(
        detector=kind,
        metric=metric,
        min_samples=5,
        threshold=200.0 if metric == "p95_latency_ms" else 20.0,
        sensitivity=3.0,
        ewma_alpha=0.3,
    )


def span(span_id: str, start: int, end: int, parent: str = ""):
    return SimpleNamespace(span_id=span_id, parent_span_id=parent, start_ns=start, end_ns=end)


def test_statistical_detectors_have_reproducible_anomaly_and_false_positive_cases():
    stable = [measured_trace(value, offset=index) for index, value in enumerate([100, 101, 99, 100, 101])]
    spike = [*stable[:-1], measured_trace(500, offset=4)]

    for kind in ("ewma", "robust_mad"):
        normal = detection_result(detector(kind), stable)
        anomaly = detection_result(detector(kind), spike)
        assert normal["state"] == "NORMAL" and not normal["firing"]
        assert anomaly["state"] == "ANOMALY" and anomaly["firing"]
        assert anomaly["anomaly_score"] >= 3

    sparse = detection_result(detector("robust_mad"), stable[:2])
    assert sparse["state"] == "INSUFFICIENT_DATA" and sparse["observed"] is None


def test_critical_path_selects_longest_parallel_branch_and_keeps_sequential_work():
    root = span("root", 0, 100)
    parallel = [root, span("slow", 0, 80, "root"), span("fast", 0, 30, "root")]
    path, duration = critical_path(parallel, root, set())
    assert path == ["root", "slow"] and duration == 100 / 1e6

    sequential = [root, span("first", 0, 40, "root"), span("second", 40, 80, "root")]
    path, duration = critical_path(sequential, root, set())
    assert path == ["root", "first", "second"] and duration == 100 / 1e6

    assert critical_path(parallel, root, {"cycle"}) == ([], None)


def add_traces(project: str, organization: str, latencies: list[float], statuses: list[str]):
    at = now()
    with SessionLocal.begin() as db:
        for index, (latency, status) in enumerate(zip(latencies, statuses, strict=True)):
            db.add(
                Trace(
                    organization_id=organization,
                    project_id=project,
                    trace_id=uuid4().hex,
                    operation="phase2/fixture",
                    service="phase2-fixture",
                    start_ns=int((at - timedelta(seconds=len(latencies) - index)).timestamp() * 1e9),
                    duration_ms=latency,
                    status=status,
                    span_count=1,
                    tokens=None,
                    issues=[],
                    critical_path=[],
                    critical_path_duration_ms=latency,
                )
            )


def test_durable_detection_and_slo_calculation_use_actual_traces(identity):
    client, project, organization, _ = identity()
    add_traces(project, organization, [100, 101, 99, 100, 500], ["ok", "ok", "ok", "ok", "error"])
    rule = client.post(
        f"/v1/rules?project_id={project}",
        json={
            "name": "Robust latency spike",
            "metric": "p95_latency_ms",
            "detector": "robust_mad",
            "threshold": 200,
            "sensitivity": 3,
            "min_samples": 5,
            "window_minutes": 15,
        },
    )
    assert rule.status_code == 201, rule.text
    slo = client.post(
        f"/v1/slos?project_id={project}",
        json={
            "name": "Fixture success",
            "sli": "success_rate",
            "objective": 80,
            "window_minutes": 60,
            "short_window_minutes": 5,
            "long_window_minutes": 15,
            "min_samples": 5,
        },
    )
    assert slo.status_code == 201, slo.text
    # Independent rule/SLO jobs may be claimed concurrently. The per-project
    # worker lock and database uniqueness constraints keep evaluations idempotent.
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda _: tick(), range(2)))
    drain()

    detections = client.get(f"/v1/detections?project_id={project}").json()["items"]
    assert len(detections) == 1
    assert detections[0]["state"] == "ANOMALY" and detections[0]["incident_id"]
    objectives = client.get(f"/v1/slos?project_id={project}").json()["items"]
    latest = objectives[0]["latest"]
    assert latest["eligible_count"] == 5 and latest["good_count"] == 4
    assert latest["compliance"] == 80 and latest["error_budget_remaining"] == 0
    assert round(latest["short_burn_rate"], 6) == 1
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Detection).where(Detection.project_id == project)) == 1
        assert db.scalar(
            select(func.count()).select_from(SLOSnapshot).where(SLOSnapshot.project_id == project)
        ) == 1


def test_new_phase2_endpoints_enforce_roles_and_project_scope(identity):
    admin, project_a, organization, _ = identity()
    viewer, _, _, _ = identity("viewer", organization_id=organization, project_id=project_a)
    _, project_b, _, _ = identity()

    body = {
        "name": "Authorization objective",
        "sli": "success_rate",
        "objective": 99,
        "window_minutes": 60,
        "short_window_minutes": 5,
        "long_window_minutes": 15,
        "min_samples": 5,
    }
    assert viewer.post(f"/v1/slos?project_id={project_a}", json=body).status_code == 403
    assert viewer.post(
        f"/v1/changes?project_id={project_a}",
        json={
            "kind": "deployment",
            "service": "phase2-fixture",
            "version": "v1",
            "description": "Authorization fixture",
            "recorded_at": now().isoformat(),
        },
    ).status_code == 403
    assert admin.get(f"/v1/slos?project_id={project_b}").status_code == 404
    assert admin.get(f"/v1/detections?project_id={project_b}").status_code == 404
    assert admin.get(f"/v1/changes?project_id={project_b}").status_code == 404


def test_change_evidence_is_persisted_without_causal_claim(identity, gateway):
    from test_vertical_slice import batch, ingest

    client, project, _, _ = identity()
    key = client.post(f"/v1/credentials?project_id={project}").json()["secret"]
    client.post(
        f"/v1/rules?project_id={project}",
        json={
            "name": "Change correlation fixture",
            "metric": "error_rate",
            "threshold": 1,
            "min_samples": 1,
        },
    )
    data = batch()
    child = data["resourceSpans"][0]["scopeSpans"][0]["spans"][1]
    child["attributes"].append(
        {"key": "service.name", "value": {"stringValue": "retrieval-service"}}
    )
    change = client.post(
        f"/v1/changes?project_id={project}",
        json={
            "kind": "deployment",
            "service": "retrieval-service",
            "version": "fixture-v2",
            "description": "Synthetic correlated deployment",
            "recorded_at": now().isoformat(),
        },
    )
    assert change.status_code == 201, change.text
    assert ingest(gateway, key, data).status_code == 200
    drain()
    incident = client.get(f"/v1/incidents?project_id={project}").json()["items"][0]
    result = client.get(
        f"/v1/incidents/{incident['id']}/hypotheses?project_id={project}"
    ).json()
    hypothesis = result["items"][0]
    assert hypothesis["evidence_class"] == "multi_source"
    assert hypothesis["change_evidence"][0]["version"] == "fixture-v2"
    assert hypothesis["dependency_context"]
    assert "does not prove causation" in hypothesis["summary"].lower()


def test_rule_lifecycle_get_patch_versions_and_delete(identity):
    client, project, organization, _ = identity()
    viewer, _, _, _ = identity("viewer", organization_id=organization, project_id=project)

    created = client.post(
        f"/v1/rules?project_id={project}",
        json={
            "name": "Lifecycle test rule",
            "metric": "error_rate",
            "threshold": 15,
            "min_samples": 5,
        },
    ).json()
    rule_id = created["id"]

    # GET /v1/rules/{id}
    fetched = client.get(f"/v1/rules/{rule_id}?project_id={project}")
    assert fetched.status_code == 200
    assert fetched.json()["name"] == "Lifecycle test rule"
    assert fetched.json()["version"] == 1

    # Unauthorized patch
    assert (
        viewer.patch(
            f"/v1/rules/{rule_id}?project_id={project}",
            json={"threshold": 25},
        ).status_code
        == 403
    )

    # Valid patch updating configuration
    patched = client.patch(
        f"/v1/rules/{rule_id}?project_id={project}",
        json={"threshold": 25, "detector": "ewma", "sensitivity": 4.0},
    )
    assert patched.status_code == 200
    assert patched.json()["threshold"] == 25
    assert patched.json()["detector"] == "ewma"
    assert patched.json()["version"] == 2

    # Verify versions endpoint reflects both versions
    versions = client.get(f"/v1/rules/{rule_id}/versions?project_id={project}").json()["items"]
    assert len(versions) == 2
    assert versions[0]["version"] == 1
    assert versions[1]["version"] == 2
    assert versions[1]["manifest"]["threshold"] == 25

    # Invalid threshold check on patch
    assert (
        client.patch(
            f"/v1/rules/{rule_id}?project_id={project}",
            json={"threshold": 150},
        ).status_code
        == 422
    )

    # DELETE /v1/rules/{id} by viewer forbidden
    assert viewer.delete(f"/v1/rules/{rule_id}?project_id={project}").status_code == 403

    # DELETE succeeds when no incident is linked
    deleted = client.delete(f"/v1/rules/{rule_id}?project_id={project}")
    assert deleted.status_code == 204
    assert client.get(f"/v1/rules/{rule_id}?project_id={project}").status_code == 404


def test_rule_delete_blocked_when_incident_linked(identity, gateway):
    from test_vertical_slice import batch, ingest

    client, project, _, _ = identity()
    key = client.post(f"/v1/credentials?project_id={project}").json()["secret"]
    rule = client.post(
        f"/v1/rules?project_id={project}",
        json={"name": "Linked incident rule", "metric": "error_rate", "threshold": 1, "min_samples": 1},
    ).json()

    ingest(gateway, key, batch())
    drain()

    # Rule now has linked incident
    incidents = client.get(f"/v1/incidents?project_id={project}").json()["items"]
    assert len(incidents) > 0
    resp = client.delete(f"/v1/rules/{rule['id']}?project_id={project}")
    assert resp.status_code == 409
    assert resp.json()["code"] == "RULE_IN_USE"


def test_incident_notes_lifecycle(identity, gateway):
    from test_vertical_slice import batch, ingest

    client, project, organization, _ = identity()
    viewer, _, _, _ = identity("viewer", organization_id=organization, project_id=project)
    key = client.post(f"/v1/credentials?project_id={project}").json()["secret"]
    client.post(
        f"/v1/rules?project_id={project}",
        json={"name": "Notes test rule", "metric": "error_rate", "threshold": 1, "min_samples": 1},
    )
    ingest(gateway, key, batch())
    drain()

    incident = client.get(f"/v1/incidents?project_id={project}").json()["items"][0]
    incident_id = incident["id"]

    # Empty notes initially
    initial = client.get(f"/v1/incidents/{incident_id}/notes?project_id={project}").json()["items"]
    assert len(initial) == 0

    # Viewer forbidden to post note
    assert (
        viewer.post(
            f"/v1/incidents/{incident_id}/notes?project_id={project}",
            json={"content": "Unauthorized note"},
        ).status_code
        == 403
    )

    # Empty content rejected
    assert (
        client.post(
            f"/v1/incidents/{incident_id}/notes?project_id={project}",
            json={"content": "   "},
        ).status_code
        == 422
    )

    # Authorized note created
    post_resp = client.post(
        f"/v1/incidents/{incident_id}/notes?project_id={project}",
        json={"content": "Investigating upstream dependency timeout."},
    )
    assert post_resp.status_code == 201
    note = post_resp.json()
    assert note["content"] == "Investigating upstream dependency timeout."
    assert note["author_name"]

    # Notes listed in chronological order
    post_resp2 = client.post(
        f"/v1/incidents/{incident_id}/notes?project_id={project}",
        json={"content": "Confirmed database connection pool saturation."},
    )
    assert post_resp2.status_code == 201

    notes = client.get(f"/v1/incidents/{incident_id}/notes?project_id={project}").json()["items"]
    assert len(notes) == 2
    assert notes[0]["content"] == "Investigating upstream dependency timeout."
    assert notes[1]["content"] == "Confirmed database connection pool saturation."




def test_incident_notes_are_database_immutable(identity, gateway):
    import pytest
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError
    from test_vertical_slice import batch, ingest

    from neuralops.db import SessionLocal

    client, project, _, _ = identity()
    key = client.post(f"/v1/credentials?project_id={project}").json()["secret"]
    client.post(f"/v1/rules?project_id={project}", json={
        "name": "Immutable notes fixture", "metric": "error_rate", "threshold": 1, "min_samples": 1,
    })
    ingest(gateway, key, batch())
    drain()
    incident = client.get(f"/v1/incidents?project_id={project}").json()["items"][0]
    response = client.post(f"/v1/incidents/{incident['id']}/notes?project_id={project}",
                           json={"content": "Preserve investigation evidence"})
    assert response.status_code == 201
    for statement in ("UPDATE incident_notes SET content='changed' WHERE id=:id",
                      "DELETE FROM incident_notes WHERE id=:id"):
        with pytest.raises(IntegrityError, match="IMMUTABLE_RECORD"), SessionLocal.begin() as db:
            db.execute(text(statement), {"id": response.json()["id"]})
