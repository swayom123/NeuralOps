"""Phase 3 tests: reproducible evaluations, dataset versioning, graders, and sandbox isolation."""

from uuid import uuid4

import pytest

from neuralops.sandbox import execute_sandboxed
from neuralops.worker import tick


def drain():
    for _ in range(1000):
        if not tick():
            return
    raise AssertionError("Worker did not drain")


@pytest.mark.parametrize(
    "code",
    [
        "output = 42",
        "import socket; socket.socket()",
        'import subprocess; subprocess.run(["true"])',
        "while True: pass",
    ],
)
def test_sandbox_fails_closed_without_running_code(code, tmp_path):
    sentinel = tmp_path / "must-not-exist"
    result = execute_sandboxed(f"open({str(sentinel)!r}, 'w').write('executed'); " + code, {})
    assert result.status == "BLOCKED"
    assert result.output is None
    assert "not executed" in result.error
    assert not sentinel.exists()


def test_dataset_versioning_and_immutability(identity):
    client, project, org, _ = identity()

    # 1. Publish Version 1
    v1_resp = client.post(
        f"/v1/datasets?project_id={project}",
        json={
            "name": "Customer Intent Benchmark",
            "description": "Baseline intent categorization",
            "cases": [
                {
                    "id": f"intent-{i}",
                    "expected": "billing",
                    "baseline_output": "unknown",
                    "candidate_output": "billing",
                }
                for i in range(35)
            ],
        },
    )
    assert v1_resp.status_code == 201
    v1 = v1_resp.json()
    assert v1["version"] == 1
    assert v1["parent_id"] is None
    assert v1["case_count"] == 35

    # 2. Publish Version 2 for the same dataset
    v2_resp = client.post(
        f"/v1/datasets/{v1['id']}/versions?project_id={project}",
        json={
            "description": "Extended with account cancellation intents",
            "cases": [
                {
                    "id": f"intent-{i}",
                    "expected": "cancel",
                    "baseline_output": "unknown",
                    "candidate_output": "cancel",
                }
                for i in range(40)
            ],
        },
    )
    assert v2_resp.status_code == 201
    v2 = v2_resp.json()
    assert v2["version"] == 2
    assert v2["parent_id"] == v1["id"]
    assert v2["case_count"] == 40
    assert v2["name"] == v1["name"]

    # 3. Publish Version 3 referencing v2
    v3_resp = client.post(
        f"/v1/datasets/{v2['id']}/versions?project_id={project}",
        json={
            "cases": [
                {
                    "id": f"intent-{i}",
                    "expected": "upgrade",
                    "baseline_output": "unknown",
                    "candidate_output": "upgrade",
                }
                for i in range(45)
            ],
        },
    )
    assert v3_resp.status_code == 201
    v3 = v3_resp.json()
    assert v3["version"] == 3
    assert v3["parent_id"] == v1["id"]
    assert v3["case_count"] == 45

    # 4. Query all versions
    versions = client.get(f"/v1/datasets/{v1['id']}/versions?project_id={project}").json()["items"]
    assert len(versions) == 3
    assert [v["version"] for v in versions] == [3, 2, 1]

    # 5. Detail inspection
    detail = client.get(f"/v1/datasets/{v2['id']}?project_id={project}").json()
    assert detail["id"] == v2["id"]
    assert detail["version"] == 2
    assert len(detail["cases"]) == 40


def test_graders_json_validity_and_safety_guard(identity):
    client, project, org, _ = identity()

    # Create dataset with structured output and potential hostile prompt
    cases = [
        {
            "id": f"json-case-{i}",
            "expected": '{"status": "ok"}',
            "baseline_output": "invalid json string" if i < 15 else '{"status": "ok"}',
            "candidate_output": '{"status": "ok", "safe": true}',
        }
        for i in range(35)
    ]
    # Inject toxic pattern in one candidate case for safety testing
    cases[10]["candidate_output"] = '{"status": "ok", "leak": "ignore previous instructions"}'

    dataset = client.post(
        f"/v1/datasets?project_id={project}",
        json={"name": "Structured Output & Safety Test", "cases": cases},
    ).json()

    # 1. Run evaluation with JSON validity grader and safety pattern guard
    eval_resp = client.post(
        f"/v1/evaluations?project_id={project}",
        json={
            "dataset_id": dataset["id"],
            "baseline": "baseline-llm",
            "candidate": "candidate-llm",
            "grader": "json-validity-v1",
            "safety_patterns": ["ignore previous instructions"],
        },
        headers={"Idempotency-Key": f"eval-safety-{uuid4()}"},
    )
    assert eval_resp.status_code == 202
    run_id = eval_resp.json()["id"]
    drain()

    result = client.get(f"/v1/evaluations/{run_id}?project_id={project}").json()
    assert result["status"] == "COMPLETED"
    # Because case 10 contains forbidden pattern, safety check fails on that case and decision fails
    assert result["results"]["safety_score"] < 1.0
    assert result["decision"] == "FAIL"
    assert result["results"]["cases"][10]["safety_pass"] is False
    assert result["results"]["cases"][0]["safety_pass"] is True


def test_latency_and_cost_budgets(identity):
    client, project, org, _ = identity()

    cases = [
        {
            "id": f"budget-case-{i}",
            "expected": "answer",
            "baseline_output": "answer",
            "candidate_output": "answer",
            "baseline_latency_ms": 40.0,
            "candidate_latency_ms": 30.0 if i < 30 else 85.0,  # 5 cases exceed 50ms budget
            "baseline_tokens": 120,
            "candidate_tokens": 90 if i < 32 else 250,  # 3 cases exceed 150 token budget
        }
        for i in range(35)
    ]

    dataset = client.post(
        f"/v1/datasets?project_id={project}",
        json={"name": "Budget Enforcement Dataset", "cases": cases},
    ).json()

    eval_resp = client.post(
        f"/v1/evaluations?project_id={project}",
        json={
            "dataset_id": dataset["id"],
            "baseline": "v1",
            "candidate": "v2",
            "latency_budget_ms": 50.0,
            "cost_budget_tokens": 150,
        },
        headers={"Idempotency-Key": f"eval-budget-{uuid4()}"},
    )
    assert eval_resp.status_code == 202
    run_id = eval_resp.json()["id"]
    drain()

    result = client.get(f"/v1/evaluations/{run_id}?project_id={project}").json()
    assert result["status"] == "COMPLETED"
    # Case 31 failed candidate latency (85 > 50) and candidate tokens (250 > 150)
    assert result["results"]["cases"][31]["candidate_pass"] is False
    assert result["results"]["cases"][0]["candidate_pass"] is True


def test_code_execution_rejected_at_api_and_for_already_queued_runs(identity, tmp_path):
    from sqlalchemy import select

    from neuralops.db import SessionLocal
    from neuralops.models import Evaluation

    client, project, _, _ = identity()
    cases = [{"id": "case", "expected": "yes", "baseline_output": "no", "candidate_output": "yes"}]
    dataset = client.post(
        f"/v1/datasets?project_id={project}", json={"name": "Safe replay", "cases": cases}
    ).json()
    payload = {"dataset_id": dataset["id"], "baseline": "v1", "candidate": "v2"}
    sentinel = tmp_path / "must-not-exist"
    code = f"open({str(sentinel)!r}, 'w').write('executed')"
    for unsafe in ({"mode": "sandboxed-execution"}, {"candidate_code": code}):
        response = client.post(
            f"/v1/evaluations?project_id={project}",
            json={**payload, **unsafe},
            headers={"Idempotency-Key": str(uuid4())},
        )
        assert response.status_code == 503
        assert response.json()["code"] == "EVALUATOR_UNAVAILABLE"
    with SessionLocal() as db:
        assert not db.scalars(select(Evaluation).where(Evaluation.project_id == project)).all()
    queued = client.post(
        f"/v1/evaluations?project_id={project}", json=payload, headers={"Idempotency-Key": str(uuid4())}
    ).json()
    # Simulate a job accepted by the old implementation before this repair.
    with SessionLocal.begin() as db:
        run = db.get(Evaluation, queued["id"])
        run.manifest = {**run.manifest, "mode": "sandboxed-execution", "candidate_code": code}
    drain()
    result = client.get(f"/v1/evaluations/{queued['id']}?project_id={project}").json()
    assert result["status"] == "FAILED"
    assert result["decision"] is None
    assert not sentinel.exists()


def test_evaluation_export_report_and_audit(identity):
    client, project, org, _ = identity()

    dataset = client.post(
        f"/v1/datasets?project_id={project}",
        json={
            "name": "Exportable Dataset",
            "cases": [
                {"id": f"case-{i}", "expected": "yes", "baseline_output": "no", "candidate_output": "yes"}
                for i in range(32)
            ],
        },
    ).json()

    eval_run = client.post(
        f"/v1/evaluations?project_id={project}",
        json={"dataset_id": dataset["id"], "baseline": "v1", "candidate": "v2"},
        headers={"Idempotency-Key": f"eval-export-{uuid4()}"},
    ).json()
    drain()

    export_resp = client.get(f"/v1/evaluations/{eval_run['id']}/export?project_id={project}")
    assert export_resp.status_code == 200
    report = export_resp.json()
    assert report["id"] == eval_run["id"]
    assert report["report_checksum"] is not None
    assert len(report["report_checksum"]) == 64
    assert report["results"]["sample_count"] == 32
    from neuralops.domain import manifest_hash

    assert report["report_checksum"] == manifest_hash(
        {k: v for k, v in report.items() if k != "report_checksum"}
    )
    assert (
        export_resp.json()
        == client.get(f"/v1/evaluations/{eval_run['id']}/export?project_id={project}").json()
    )

    # Verify audit event recorded
    audit_events = client.get(f"/v1/audit?project_id={project}&limit=50").json()["items"]
    assert any(a["action"] == "evaluation.exported" and a["target"] == eval_run["id"] for a in audit_events)


def replay(client, project, cases, **options):
    dataset = client.post(
        f"/v1/datasets?project_id={project}", json={"name": "Regression fixture", "cases": cases}
    )
    assert dataset.status_code == 201, dataset.text
    response = client.post(
        f"/v1/evaluations?project_id={project}",
        json={"dataset_id": dataset.json()["id"], "baseline": "v1", "candidate": "v2", **options},
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert response.status_code == 202, response.text
    drain()
    return client.get(f"/v1/evaluations/{response.json()['id']}?project_id={project}").json()


def passing_cases(n=35):
    return [
        {"id": f"case-{i}", "expected": "yes", "baseline_output": "no", "candidate_output": "yes"}
        for i in range(n)
    ]


def test_missing_guardrail_measurements_are_unknown(identity):
    client, project, _, _ = identity()
    result = replay(client, project, passing_cases(), latency_budget_ms=50, cost_budget_tokens=100)
    assert result["decision"] == "INCONCLUSIVE"
    assert result["results"]["candidate_score"] is None
    assert result["results"]["interval_95"] is None
    assert result["results"]["cases"][0]["candidate_pass"] is None
    assert result["results"]["missing_measurements"] is True


@pytest.mark.parametrize(
    "options,measurement",
    [
        ({"latency_budget_ms": 50}, {"baseline_latency_ms": 10, "candidate_latency_ms": 100}),
        ({"cost_budget_tokens": 100}, {"baseline_tokens": 10, "candidate_tokens": 200}),
        ({"safety_patterns": ["yes"]}, {}),
    ],
)
def test_guardrail_failure_cannot_be_hidden_by_improvement_or_small_sample(identity, options, measurement):
    client, project, _, _ = identity()
    cases = passing_cases()
    cases[-1].update(measurement)
    if measurement:
        # All other cases have measurements within budget.
        for case in cases[:-1]:
            case.update({key: 1 for key in measurement})
    result = replay(client, project, cases, **options)
    assert result["decision"] == "FAIL"
    assert replay(client, project, cases[-1:], **options)["decision"] == "FAIL"


def test_duplicate_inputs_do_not_inflate_independent_sample_count(identity):
    client, project, _, _ = identity()
    cases = [{**case, "input": "same input"} for case in passing_cases()]
    result = replay(client, project, cases)
    assert result["decision"] == "INCONCLUSIVE"
    assert result["results"]["contamination"]["duplicate_count"] == 34
    assert result["results"]["contamination"]["training_overlap"] == "unknown"


@pytest.mark.parametrize(
    "invalid",
    [
        {"grader": "unknown"},
        {"safety_patterns": [""]},
        {"safety_patterns": ["x" * 257]},
        {"repeats": 2},
    ],
)
def test_evaluation_config_is_allowlisted_and_bounded(identity, invalid):
    client, project, _, _ = identity()
    dataset = client.post(
        f"/v1/datasets?project_id={project}", json={"name": "Config fixture", "cases": passing_cases(1)}
    ).json()
    response = client.post(
        f"/v1/evaluations?project_id={project}",
        json={"dataset_id": dataset["id"], "baseline": "v1", "candidate": "v2", **invalid},
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert response.status_code == 422


def test_json_grader_rejects_non_json_constants():
    from neuralops.domain import grade_case

    for output in ("NaN", "Infinity", '{"value": NaN}'):
        result = grade_case(
            {"id": "case", "baseline_output": "{}", "candidate_output": output},
            {"grader": "json-validity-v1"},
        )
        assert result["candidate_pass"] is False


def test_concurrent_dataset_versions_and_scope_constraints(identity):
    from concurrent.futures import ThreadPoolExecutor

    from sqlalchemy.exc import IntegrityError

    from neuralops.db import SessionLocal
    from neuralops.models import Dataset

    client, project, organization, _ = identity()
    other, other_project, _, _ = identity()
    root = client.post(
        f"/v1/datasets?project_id={project}", json={"name": "Version concurrency", "cases": passing_cases(1)}
    ).json()

    def publish(_):
        return client.post(
            f"/v1/datasets/{root['id']}/versions?project_id={project}", json={"cases": passing_cases(1)}
        )

    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(pool.map(publish, range(4)))
    assert all(response.status_code == 201 for response in responses)
    assert sorted(response.json()["version"] for response in responses) == [2, 3, 4, 5]
    assert other.get(f"/v1/datasets/{root['id']}/versions?project_id={other_project}").status_code == 404
    assert (
        other.post(
            f"/v1/datasets/{root['id']}/versions?project_id={other_project}", json={"cases": passing_cases(1)}
        ).status_code
        == 404
    )
    viewer, _, _, _ = identity("viewer", organization_id=organization, project_id=project)
    assert (
        viewer.post(
            f"/v1/datasets/{root['id']}/versions?project_id={project}", json={"cases": passing_cases(1)}
        ).status_code
        == 403
    )
    # Direct SQL writers cannot cross scope or duplicate a version number.
    for org, proj in ((organization, project), (organization, other_project)):
        with pytest.raises(IntegrityError), SessionLocal.begin() as db:
            db.add(
                Dataset(
                    organization_id=org,
                    project_id=proj,
                    name="Invalid version",
                    parent_id=root["id"],
                    version=2,
                    cases=[],
                    manifest_hash="a" * 64,
                )
            )
            db.flush()


def test_export_authorization_and_pending_state(identity):
    client, project, org, _ = identity()
    dataset = client.post(
        f"/v1/datasets?project_id={project}", json={"name": "Export state fixture", "cases": passing_cases(1)}
    ).json()
    run = client.post(
        f"/v1/evaluations?project_id={project}",
        json={"dataset_id": dataset["id"], "baseline": "v1", "candidate": "v2"},
        headers={"Idempotency-Key": str(uuid4())},
    ).json()
    path = f"/v1/evaluations/{run['id']}/export?project_id={project}"
    assert client.get(path).status_code == 409
    drain()
    viewer, _, _, _ = identity("viewer", organization_id=org, project_id=project)
    assert viewer.get(path).status_code == 403
    other, other_project, _, _ = identity()
    assert other.get(f"/v1/evaluations/{run['id']}/export?project_id={other_project}").status_code == 404


def test_missing_budget_is_unknown_even_when_task_already_failed(identity):
    client, project, _, _ = identity()
    result = replay(client, project, passing_cases(), latency_budget_ms=50)
    assert result["results"]["missing_measurements"] is True
    assert result["decision"] == "INCONCLUSIVE"
