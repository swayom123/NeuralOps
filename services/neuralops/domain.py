import hashlib
import json
import math
import statistics
from collections import Counter
from datetime import timedelta

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from .db import audit
from .models import (
    SLO,
    ChangeEvent,
    Dataset,
    Detection,
    Evaluation,
    EvidenceLink,
    Hypothesis,
    Incident,
    Job,
    Rule,
    SLOSnapshot,
    Span,
    Trace,
    now,
)


def manifest_hash(data: dict | list) -> str:
    return hashlib.sha256(
        json.dumps(data, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def percentile(values: list[float], quantile: float) -> float | None:
    """Nearest-rank percentile: sorted[ceil(q*n)-1]."""
    return sorted(values)[max(0, math.ceil(quantile * len(values)) - 1)] if values else None


def interval_union_ns(intervals: list[tuple[int, int]]) -> int:
    merged: list[list[int]] = []
    for start, end in sorted((start, end) for start, end in intervals if end > start):
        if not merged or start >= merged[-1][1]:
            merged.append([start, end])
        else:
            merged[-1][1] = max(merged[-1][1], end)
    return sum(end - start for start, end in merged)


def critical_path(spans: list[Span], root: Span, issues: set[str]) -> tuple[list[str], float | None]:
    """Infer a hierarchical critical path while counting overlapping children only once."""
    if not root.end_ns or issues & {"cycle", "missing_root", "multiple_roots"}:
        return [], None
    children: dict[str, list[Span]] = {}
    for span in spans:
        children.setdefault(span.parent_span_id, []).append(span)

    def visit(span: Span, seen: set[str]) -> tuple[int, list[Span]]:
        if span.span_id in seen or not span.end_ns:
            return 0, []
        direct = [
            child
            for child in children.get(span.span_id, [])
            if child.end_ns and child.start_ns >= span.start_ns and child.end_ns <= span.end_ns
        ]
        child_results = [(child, *visit(child, seen | {span.span_id})) for child in direct]
        exclusive = max(
            0,
            span.end_ns
            - span.start_ns
            - interval_union_ns([(child.start_ns, child.end_ns) for child in direct]),
        )
        groups: list[list[tuple[Span, int, list[Span]]]] = []
        group_end = -1
        for result in sorted(child_results, key=lambda item: (item[0].start_ns, item[0].end_ns)):
            child = result[0]
            if not groups or child.start_ns >= group_end:
                groups.append([result])
                group_end = child.end_ns
            else:
                groups[-1].append(result)
                group_end = max(group_end, child.end_ns)
        selected = [max(group, key=lambda item: (item[1], item[0].end_ns)) for group in groups]
        duration = exclusive + sum(item[1] for item in selected)
        path = [span]
        for _, _, child_path in selected:
            path.extend(child_path)
        return duration, path

    duration_ns, path = visit(root, set())
    ordered = sorted({span.span_id: span for span in path}.values(), key=lambda span: span.start_ns)
    return [span.span_id for span in ordered], duration_ns / 1e6


def scope(model, org: str, project: str):
    return (model.organization_id == org, model.project_id == project)


def queue_diagnosis(db: Session, incident: Incident):
    pending = db.scalar(
        select(Job.id)
        .where(
            *scope(Job, incident.organization_id, incident.project_id),
            Job.kind == "diagnosis",
            Job.resource_id == incident.id,
            Job.status.in_(["QUEUED", "RUNNING"]),
        )
        .limit(1)
    )
    if not pending:
        db.add(
            Job(
                organization_id=incident.organization_id,
                project_id=incident.project_id,
                kind="diagnosis",
                resource_id=incident.id,
            )
        )


def reconstruct(db: Session, job: Job):
    spans = list(
        db.scalars(
            select(Span).where(
                *scope(Span, job.organization_id, job.project_id),
                Span.trace_id == job.resource_id,
            )
        )
    )
    if not spans:
        return
    lookup = {s.span_id: s for s in spans}
    roots, issues = [s for s in spans if not s.parent_span_id], set()
    for span in spans:
        if span.parent_span_id and span.parent_span_id not in lookup:
            issues.add("missing_parent")
        if not span.end_ns:
            issues.add("incomplete_span")
        if span.start_ns > int(now().timestamp() * 1e9) + 300_000_000_000:
            issues.add("future_timestamp")
        seen, current = set(), span
        while current:
            if current.span_id in seen:
                issues.add("cycle")
                break
            seen.add(current.span_id)
            parent = lookup.get(current.parent_span_id)
            if parent and (
                current.start_ns < parent.start_ns or (parent.end_ns and current.end_ns > parent.end_ns)
            ):
                issues.add("clock_skew_or_outside_parent")
            current = parent
    if len(roots) != 1:
        issues.add("missing_root" if not roots else "multiple_roots")
    root = min(roots or spans, key=lambda s: s.start_ns)
    duration = (root.end_ns - root.start_ns) / 1e6 if root.end_ns and len(roots) == 1 else None
    path, path_duration = critical_path(spans, root, issues)
    if duration is not None and not path:
        issues.add("critical_path_unavailable")
    token_values = [
        value
        for span in spans
        for key, value in span.attributes.items()
        if key in {"gen_ai.usage.input_tokens", "gen_ai.usage.output_tokens"}
    ]
    # Attribute token usage to leaf model spans only; ancestor/child duplicated usage is ambiguous.
    measured_ids = {
        s.span_id
        for s in spans
        if any(k in s.attributes for k in ("gen_ai.usage.input_tokens", "gen_ai.usage.output_tokens"))
    }
    ambiguous = False
    for span in spans:
        if span.span_id not in measured_ids:
            continue
        parent, seen = lookup.get(span.parent_span_id), set()
        while parent and parent.span_id not in seen:
            seen.add(parent.span_id)
            if parent.span_id in measured_ids:
                ambiguous = True
                break
            parent = lookup.get(parent.parent_span_id)
    if ambiguous:
        tokens = None
        issues.add("ambiguous_token_attribution")
    else:
        tokens = sum(token_values) if token_values else None
    values = {
        "organization_id": job.organization_id,
        "project_id": job.project_id,
        "trace_id": job.resource_id,
        "operation": root.operation,
        "service": root.service,
        "start_ns": root.start_ns,
        "duration_ms": duration,
        "status": "incomplete"
        if issues - {"ambiguous_token_attribution"}
        else "error"
        if any(s.status == "error" for s in spans)
        else "ok",
        "span_count": len(spans),
        "tokens": tokens,
        "issues": sorted(issues),
        "critical_path": path,
        "critical_path_duration_ms": path_duration,
    }
    statement = insert(Trace).values(**values)
    db.execute(
        statement.on_conflict_do_update(
            index_elements=["organization_id", "project_id", "trace_id"],
            set_={k: v for k, v in values.items() if k not in {"organization_id", "project_id", "trace_id"}},
        )
    )


def metric_values(rule: Rule, traces: list[Trace]) -> list[float]:
    ordered = sorted(traces, key=lambda trace: (trace.start_ns, trace.id))
    if rule.metric == "error_rate":
        return [100.0 if trace.status == "error" else 0.0 for trace in ordered]
    return [trace.duration_ms for trace in ordered if trace.duration_ms is not None]


def detection_result(rule: Rule, traces: list[Trace], oversized: bool = False) -> dict:
    values = metric_values(rule, traces)
    if oversized or len(values) < rule.min_samples or (rule.detector != "threshold" and len(values) < 3):
        return {
            "state": "INSUFFICIENT_DATA",
            "observed": None,
            "baseline": None,
            "deviation": None,
            "anomaly_score": None,
            "sample_count": len(values),
            "firing": False,
        }
    if rule.detector == "threshold":
        observed = sum(values) / len(values) if rule.metric == "error_rate" else percentile(values, 0.95)
        return {
            "state": "ANOMALY" if observed is not None and observed > rule.threshold else "NORMAL",
            "observed": observed,
            "baseline": None,
            "deviation": observed - rule.threshold if observed is not None else None,
            "anomaly_score": None,
            "sample_count": len(values),
            "firing": observed is not None and observed > rule.threshold,
        }
    history, observed = values[:-1], values[-1]
    if rule.detector == "ewma":
        baseline = history[0]
        residuals: list[float] = []
        for value in history[1:]:
            residuals.append(abs(value - baseline))
            baseline = rule.ewma_alpha * value + (1 - rule.ewma_alpha) * baseline
        scale = sum(residuals) / len(residuals) if residuals else 0.0
    else:
        baseline = statistics.median(history)
        deviations = [abs(value - baseline) for value in history]
        scale = 1.4826 * statistics.median(deviations)
        if scale == 0 and deviations:
            scale = sum(deviations) / len(deviations)
    scale = max(scale, abs(baseline) * 0.01, 0.001)
    deviation = observed - baseline
    score = min(100.0, max(0.0, deviation / scale))
    firing = observed > rule.threshold and score >= rule.sensitivity
    return {
        "state": "ANOMALY" if firing else "NORMAL",
        "observed": observed,
        "baseline": baseline,
        "deviation": deviation,
        "anomaly_score": score,
        "sample_count": len(values),
        "firing": firing,
    }


def persist_detection(
    db: Session,
    rule: Rule,
    result: dict,
    evidence: list[str],
    start,
    end,
) -> Detection:
    dedup_key = f"{rule.id}:{int(end.timestamp() // 60)}"
    values = {
        "organization_id": rule.organization_id,
        "project_id": rule.project_id,
        "rule_id": rule.id,
        "dedup_key": dedup_key,
        "detector": rule.detector,
        "metric": rule.metric,
        "state": result["state"],
        "observed": result["observed"],
        "baseline": result["baseline"],
        "deviation": result["deviation"],
        "anomaly_score": result["anomaly_score"],
        "threshold": rule.threshold,
        "sample_count": result["sample_count"],
        "window_start": start,
        "window_end": end,
        "evidence": evidence,
        "evaluated_at": end,
    }
    statement = insert(Detection).values(**values)
    db.execute(
        statement.on_conflict_do_update(
            index_elements=["organization_id", "project_id", "dedup_key"],
            set_={
                key: value for key, value in values.items() if key not in {"organization_id", "project_id"}
            },
        )
    )
    return db.scalar(
        select(Detection).where(
            *scope(Detection, rule.organization_id, rule.project_id), Detection.dedup_key == dedup_key
        )
    )


def slo_counts(slo: SLO, traces: list[Trace]) -> tuple[int, int]:
    eligible = [trace for trace in traces if trace.status != "incomplete"]
    if slo.sli == "success_rate":
        good = sum(trace.status == "ok" for trace in eligible)
    else:
        good = sum(
            trace.duration_ms is not None and trace.duration_ms <= slo.latency_threshold_ms
            for trace in eligible
        )
    return len(eligible), good


def burn_rate(slo: SLO, traces: list[Trace]) -> float | None:
    eligible, good = slo_counts(slo, traces)
    if eligible < slo.min_samples:
        return None
    budget = 1 - slo.objective / 100
    return (1 - good / eligible) / budget


def calculate_slos(db: Session, org: str, project: str, evaluated_at=None):
    at = evaluated_at or now()
    slos = list(
        db.scalars(select(SLO).where(*scope(SLO, org, project), SLO.enabled.is_(True)).order_by(SLO.id))
    )
    if not slos:
        return
    maximum = max(max(slo.window_minutes, slo.long_window_minutes) for slo in slos)
    cutoff = int((at - timedelta(minutes=maximum)).timestamp() * 1e9)
    traces = list(
        db.scalars(
            select(Trace)
            .where(*scope(Trace, org, project), Trace.start_ns.between(cutoff, int(at.timestamp() * 1e9)))
            .order_by(Trace.start_ns, Trace.id)
            .limit(10_001)
        )
    )
    oversized = len(traces) > 10_000
    if oversized:
        traces = []
    for slo in slos:

        def window(minutes: int) -> list[Trace]:
            start_ns = int((at - timedelta(minutes=minutes)).timestamp() * 1e9)
            return [trace for trace in traces if trace.start_ns >= start_ns]

        total = window(slo.window_minutes)
        eligible, good = slo_counts(slo, total)
        enough = not oversized and eligible >= slo.min_samples
        compliance = good / eligible * 100 if enough else None
        budget = 1 - slo.objective / 100
        bad_rate = 1 - good / eligible if enough else None
        remaining = max(0.0, min(100.0, (budget - bad_rate) / budget * 100)) if enough else None
        short = burn_rate(slo, window(slo.short_window_minutes)) if not oversized else None
        long = burn_rate(slo, window(slo.long_window_minutes)) if not oversized else None
        status = (
            "INSUFFICIENT_DATA"
            if not enough
            else "BREACHING"
            if compliance < slo.objective
            or (short is not None and long is not None and short >= 14.4 and long >= 6)
            else "HEALTHY"
        )
        values = {
            "organization_id": org,
            "project_id": project,
            "slo_id": slo.id,
            "calculated_minute": int(at.timestamp() // 60),
            "status": status,
            "eligible_count": eligible,
            "good_count": good,
            "compliance": compliance,
            "error_budget_remaining": remaining,
            "short_burn_rate": short,
            "long_burn_rate": long,
            "window_start": at - timedelta(minutes=slo.window_minutes),
            "window_end": at,
            "calculated_at": at,
        }
        statement = insert(SLOSnapshot).values(**values)
        db.execute(
            statement.on_conflict_do_update(
                index_elements=["slo_id", "calculated_minute"],
                set_={
                    key: value
                    for key, value in values.items()
                    if key not in {"organization_id", "project_id"}
                },
            )
        )


def detect(db: Session, org: str, project: str):
    evaluated_at = now()
    rules = db.scalars(
        select(Rule)
        .where(*scope(Rule, org, project), Rule.enabled.is_(True), Rule.deleted_at.is_(None))
        .order_by(Rule.id)
        .with_for_update()
    ).all()
    for rule in rules:
        start = evaluated_at - timedelta(minutes=rule.window_minutes)
        traces = list(
            db.scalars(
                select(Trace)
                .where(
                    *scope(Trace, org, project),
                    Trace.start_ns.between(int(start.timestamp() * 1e9), int(evaluated_at.timestamp() * 1e9)),
                    Trace.status != "incomplete",
                )
                .order_by(Trace.start_ns, Trace.id)
                .limit(10_001)
            )
        )
        oversized = len(traces) > 10_000
        if oversized:
            traces = traces[:10_000]
        result = detection_result(rule, traces, oversized)
        evidence = [
            trace.trace_id
            for trace in sorted(
                traces,
                key=lambda trace: (trace.status != "error", -(trace.duration_ms or 0), trace.trace_id),
            )[:20]
        ]
        detection = persist_detection(db, rule, result, evidence, start, evaluated_at)
        rule.last_observed = result["observed"]
        rule.state = (
            "insufficient_data"
            if result["state"] == "INSUFFICIENT_DATA"
            else "firing"
            if result["firing"]
            else "ok"
        )
        if not result["firing"]:
            continue
        # Rule lock serializes grouping across workers. Active incident always wins over a new window.
        active = db.scalar(
            select(Incident).where(
                *scope(Incident, org, project),
                Incident.rule_id == rule.id,
                Incident.status != "RESOLVED",
            )
        )
        if active:
            evidence_changed = active.evidence != evidence
            active.observed, active.sample_count, active.evidence, active.updated_at = (
                result["observed"],
                result["sample_count"],
                evidence,
                evaluated_at,
            )
            detection.incident_id = active.id
            if evidence_changed:
                queue_diagnosis(db, active)
            continue
        if (
            rule.last_fired_at
            and rule.last_fired_at + timedelta(minutes=rule.cooldown_minutes) > evaluated_at
        ):
            continue
        incident = Incident(
            organization_id=org,
            project_id=project,
            rule_id=rule.id,
            dedup_key=detection.dedup_key,
            title=rule.name,
            severity=rule.severity,
            observed=result["observed"],
            threshold=rule.threshold,
            sample_count=result["sample_count"],
            evidence=evidence,
            timeline=[
                {
                    "action": "detected",
                    "actor": "detection-worker",
                    "at": evaluated_at.isoformat(),
                    "rule_version": rule.version,
                    "metric": rule.metric,
                    "detector": rule.detector,
                    "window_minutes": rule.window_minutes,
                }
            ],
        )
        db.add(incident)
        db.flush()
        detection.incident_id = incident.id
        queue_diagnosis(db, incident)
        audit(db, org, "worker", "incident.created", incident.id, project_id=project)
        rule.last_fired_at = evaluated_at
    calculate_slos(db, org, project, evaluated_at)


def grade_case(case: dict, manifest: dict) -> dict:
    expected = case.get("expected", "")
    baseline_output = case.get("baseline_output", "")
    candidate_output = case.get("candidate_output", "")
    grader = manifest.get("grader", "exact-match-v1")

    def task_pass(output: str) -> bool:
        if grader == "exact-match-v1":
            return output == expected
        if grader == "json-validity-v1":
            try:
                # Python otherwise accepts non-JSON NaN/Infinity constants.
                def reject_constant(value: str):
                    raise ValueError("Non-JSON constant")

                json.loads(output, parse_constant=reject_constant)
                return True
            except (ValueError, TypeError):
                return False
        raise ValueError("UNKNOWN_GRADER")

    patterns = manifest.get("safety_patterns") or []
    checks = {}
    for side, output in (("baseline", baseline_output), ("candidate", candidate_output)):
        safety = not any(p.lower() in output.lower() for p in patterns)
        checks[f"{side}_safety_pass"] = safety
        checks[f"{side}_task_pass"] = task_pass(output)
        for label, field, budget in (
            ("latency", "latency_ms", manifest.get("latency_budget_ms")),
            ("token", "tokens", manifest.get("cost_budget_tokens")),
        ):
            value = case.get(f"{side}_{field}")
            checks[f"{side}_{label}_pass"] = (
                True if budget is None else (None if value is None else value <= budget)
            )
        values = [value for key, value in checks.items() if key.startswith(f"{side}_")]
        checks[f"{side}_pass"] = False if False in values else (None if None in values else True)
    return {
        "id": case["id"],
        **checks,
        "safety_pass": checks["candidate_safety_pass"],
        "task_pass": checks["candidate_task_pass"],
    }


def detect_contamination(cases: list[dict]) -> dict:
    """Within-dataset duplicate checks only; training/tuning overlap is unknown."""
    seen_ids = set()
    seen_inputs: dict[str, str] = {}
    duplicates = []
    conflicts = []
    for case in cases:
        if case["id"] in seen_ids:
            duplicates.append(case["id"])
        seen_ids.add(case["id"])
        payload = case.get("input")
        if payload:
            if payload in seen_inputs:
                duplicates.append(case["id"])
                if seen_inputs[payload] != case["expected"]:
                    conflicts.append(case["id"])
            seen_inputs[payload] = case["expected"]
    return {
        "detected": bool(duplicates or conflicts),
        "duplicate_count": len(duplicates),
        "conflicting_label_count": len(conflicts),
        "details": (duplicates + conflicts)[:10],
        "scope": "within-dataset-only",
        "training_overlap": "unknown",
    }


def evaluate(db: Session, job: Job):
    run = db.scalar(
        select(Evaluation)
        .where(
            Evaluation.id == job.resource_id,
            *scope(Evaluation, job.organization_id, job.project_id),
        )
        .with_for_update()
    )
    if not run or run.status == "COMPLETED":
        return
    dataset = db.scalar(
        select(Dataset).where(
            Dataset.id == run.dataset_id,
            *scope(Dataset, job.organization_id, job.project_id),
        )
    )
    if not dataset or manifest_hash(dataset.cases) != dataset.manifest_hash:
        raise ValueError("DATASET_INTEGRITY")

    manifest = run.manifest or {}
    mode = manifest.get("mode", "offline-paired-replay")
    if mode != "offline-paired-replay" or manifest.get("candidate_code") is not None:
        run.status, run.decision = "FAILED", None
        run.results = {"limitations": "Isolated evaluation executor unavailable; no code was executed."}
        audit(
            db,
            job.organization_id,
            "evaluation-worker",
            "evaluation.blocked",
            run.id,
            outcome="denied",
            project_id=job.project_id,
        )
        return
    if manifest.get("repeats", 1) != 1:
        raise ValueError("UNSUPPORTED_REPEATS")
    contamination = detect_contamination(dataset.cases)
    results = [grade_case(case, manifest) for case in dataset.cases]
    missing_measurements = any(
        result[key] is None
        for result in results
        for key in (
            "baseline_latency_pass",
            "candidate_latency_pass",
            "baseline_token_pass",
            "candidate_token_pass",
        )
    )
    n = len(results)
    b = sum(r["baseline_pass"] is True for r in results)
    c = sum(r["candidate_pass"] is True for r in results)
    safety_passes = sum(r.get("safety_pass", True) for r in results)

    deltas = [int(r["candidate_pass"] is True) - int(r["baseline_pass"] is True) for r in results]
    mean = sum(deltas) / n if n > 0 else 0.0
    # Distribution-free paired Hoeffding interval for bounded differences in [-1, 1].
    radius = math.sqrt(2 * math.log(40) / n) if n > 0 else 1.0
    lower, upper = max(-1.0, mean - radius), min(1.0, mean + radius)

    guardrail_failed = any(
        r[key] is False
        for r in results
        for key in ("candidate_safety_pass", "candidate_latency_pass", "candidate_token_pass")
    )
    if guardrail_failed:
        decision = "FAIL"
    elif n < 30 or missing_measurements or contamination["detected"]:
        decision = "INCONCLUSIVE"
    elif lower <= 0 <= upper:
        decision = "INCONCLUSIVE"
    elif lower > 0:
        decision = "PASS"
    else:
        decision = "FAIL"

    run.results = {
        "cases": results,
        "sample_count": n,
        "baseline_score": None if missing_measurements else b / n,
        "candidate_score": None if missing_measurements else c / n,
        "safety_score": safety_passes / n if n > 0 else 1.0,
        "paired_delta": None if missing_measurements else mean,
        "interval_95": None if missing_measurements else [lower, upper],
        "repeats": 1,
        "missing_measurements": missing_measurements,
        "measurement_source": "user-supplied replay fixtures; not independently measured",
        "grader": manifest.get("grader", "exact-match-v1"),
        "contamination": contamination,
        "method": "paired-hoeffding-v1",
        "limitations": "Replay grading only; no live candidate execution. Token budgets are not monetary cost. "
        "Literal safety patterns do not certify safety; training/tuning contamination is unknown. "
        "PASS requires a positive paired lower bound, complete guardrail measurements, no detected "
        "duplicate inputs, and at least 30 cases.",
    }
    run.status, run.decision = "COMPLETED", decision
    audit(
        db,
        job.organization_id,
        "evaluation-worker",
        "evaluation.completed",
        run.id,
        project_id=job.project_id,
    )


def diagnosis(db: Session, incident: Incident) -> list[dict]:
    spans = db.scalars(
        select(Span)
        .where(
            *scope(Span, incident.organization_id, incident.project_id),
            Span.trace_id.in_(incident.evidence),
        )
        .limit(5000)
    ).all()
    lookup = {(span.trace_id, span.span_id): span for span in spans}
    dependency_edges = {
        (parent.service, span.service)
        for span in spans
        if (parent := lookup.get((span.trace_id, span.parent_span_id))) and parent.service != span.service
    }
    changes = list(
        db.scalars(
            select(ChangeEvent)
            .where(
                *scope(ChangeEvent, incident.organization_id, incident.project_id),
                ChangeEvent.recorded_at >= incident.created_at - timedelta(minutes=60),
                ChangeEvent.recorded_at <= incident.created_at + timedelta(minutes=5),
            )
            .order_by(ChangeEvent.recorded_at.desc())
            .limit(100)
        )
    )
    failures = Counter(s.service for s in spans if s.status == "error")
    result = []
    for service, count in failures.most_common(5):
        supporting = [s for s in spans if s.service == service and s.status == "error"]
        contradicting = [s for s in spans if s.service == service and s.status != "error"]
        related = sorted(
            {
                f"{source} → {target}"
                for source, target in dependency_edges
                if source == service or target == service
            }
        )
        correlated = [change for change in changes if change.service == service][:10]
        coverage = (
            len({span.trace_id for span in supporting}) / len(incident.evidence)
            if incident.evidence
            else None
        )
        missing = ["Controlled recovery experiment", "Independent downstream health measurements"]
        if not correlated:
            missing.insert(0, "Deployment/configuration change history for this service and time window")
        evidence_class = "multi_source" if correlated and related else "partial"
        result.append(
            {
                "id": service,
                "rank": 0,
                "title": f"Failures observed in {service}",
                "evidence_class": evidence_class,
                "algorithm": "failure-propagation-v2",
                "summary": (
                    f"{count} error spans across {len({span.trace_id for span in supporting})} linked traces; "
                    f"{len(related)} observed dependency edges and {len(correlated)} temporally aligned changes. "
                    "Correlation does not prove causation."
                ),
                "supporting": [
                    {
                        "trace_id": s.trace_id,
                        "span_id": s.span_id,
                        "operation": s.operation,
                    }
                    for s in supporting[:10]
                ],
                "contradicting": [
                    {"trace_id": s.trace_id, "span_id": s.span_id, "operation": s.operation}
                    for s in contradicting[:10]
                ],
                "counterevidence": f"{len(contradicting)} non-error spans for the same service are retained as contradictory evidence.",
                "missing": missing,
                "coverage": coverage,
                "dependency_context": related,
                "change_evidence": [
                    {
                        "id": change.id,
                        "kind": change.kind,
                        "service": change.service,
                        "version": change.version,
                        "description": change.description,
                        "recorded_at": change.recorded_at.isoformat(),
                    }
                    for change in correlated
                ],
                "ranking_score": count + len(related) + 2 * len(correlated),
            }
        )
    result.sort(key=lambda item: (-item.pop("ranking_score"), item["id"]))
    for rank, item in enumerate(result, 1):
        item["rank"] = rank
    return result


def persist_diagnosis(db: Session, job: Job):
    incident = db.scalar(
        select(Incident)
        .where(Incident.id == job.resource_id, *scope(Incident, job.organization_id, job.project_id))
        .with_for_update()
    )
    if not incident:
        return
    generated = diagnosis(db, incident)
    hypothesis_ids = select(Hypothesis.id).where(
        *scope(Hypothesis, job.organization_id, job.project_id),
        Hypothesis.incident_id == incident.id,
    )
    db.execute(
        delete(EvidenceLink).where(
            *scope(EvidenceLink, job.organization_id, job.project_id),
            EvidenceLink.hypothesis_id.in_(hypothesis_ids),
        )
    )
    db.execute(
        delete(Hypothesis).where(
            *scope(Hypothesis, job.organization_id, job.project_id),
            Hypothesis.incident_id == incident.id,
        )
    )
    for item in generated:
        supporting = item.pop("supporting")
        contradicting = item.pop("contradicting")
        hypothesis = Hypothesis(
            organization_id=job.organization_id,
            project_id=job.project_id,
            incident_id=incident.id,
            **{key: value for key, value in item.items() if key != "id"},
        )
        db.add(hypothesis)
        db.flush()
        for evidence in supporting:
            db.add(
                EvidenceLink(
                    organization_id=job.organization_id,
                    project_id=job.project_id,
                    hypothesis_id=hypothesis.id,
                    kind="supporting",
                    **evidence,
                )
            )
        for evidence in contradicting:
            db.add(
                EvidenceLink(
                    organization_id=job.organization_id,
                    project_id=job.project_id,
                    hypothesis_id=hypothesis.id,
                    kind="contradicting",
                    **evidence,
                )
            )
    audit(
        db,
        job.organization_id,
        "diagnosis-worker",
        "diagnosis.completed",
        incident.id,
        project_id=job.project_id,
    )
