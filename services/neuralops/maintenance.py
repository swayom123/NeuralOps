"""Bounded maintenance, invoked by the worker or the deployment administrator."""

from datetime import timedelta

from sqlalchemy import delete, select, text
from sqlalchemy.dialects.postgresql import insert

from .db import SessionLocal, audit
from .models import SLO, ExpiredTrace, Job, Project, RateBucket, Rule, Span, Trace, UserSession, now


def retain_project(db, project: Project) -> int:
    db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:scope, 0))"),
        {"scope": f"{project.organization_id}:{project.id}"},
    )
    cutoff = int((now() - timedelta(days=project.retention_days)).timestamp() * 1e9)
    expired = list(
        db.execute(
            select(Span.trace_id)
            .where(
                Span.organization_id == project.organization_id,
                Span.project_id == project.id,
                Span.start_ns < cutoff,
            )
            .distinct()
            .limit(1000)
        ).scalars()
    )
    if not expired:
        return 0
    for trace_id in expired:
        db.execute(
            insert(ExpiredTrace)
            .values(organization_id=project.organization_id, project_id=project.id, trace_id=trace_id)
            .on_conflict_do_nothing(index_elements=["organization_id", "project_id", "trace_id"])
        )
    # Delete whole expired traces consistently rather than leaving dangling partial graphs.
    for model in (Span, Trace):
        db.execute(
            delete(model).where(
                model.organization_id == project.organization_id,
                model.project_id == project.id,
                model.trace_id.in_(expired),
            )
        )
    audit(
        db,
        project.organization_id,
        "retention-worker",
        "telemetry.expired",
        project.id,
        project_id=project.id,
    )
    return len(expired)


def schedule():
    minute = int(now().timestamp() // 60)
    with SessionLocal.begin() as db:
        if not db.scalar(text("SELECT pg_try_advisory_xact_lock(736451982)")):
            return
        # Shared once-per-minute scheduler; survives process restarts and multiple workers.
        marker = db.get(RateBucket, ("maintenance", minute))
        if marker:
            return
        db.add(RateBucket(key="maintenance", minute=minute, count=1))
        db.execute(delete(RateBucket).where(RateBucket.minute < minute - 2))
        db.execute(delete(UserSession).where(UserSession.expires_at < now()))
        # Final-attempt crashes must not strand RUNNING jobs forever.
        exhausted = db.scalars(
            select(Job)
            .where(Job.status == "RUNNING", Job.lease_until < now(), Job.attempts >= 5)
            .with_for_update(skip_locked=True)
            .limit(100)
        ).all()
        for job in exhausted:
            job.status, job.lease_until, job.last_error = "DEAD_LETTER", None, "LEASE_EXHAUSTED"
        projects = db.scalars(select(Project).order_by(Project.id).limit(1000)).all()
        for project in projects:
            has_rule = db.scalar(
                select(Rule.id)
                .where(
                    Rule.organization_id == project.organization_id,
                    Rule.project_id == project.id,
                    Rule.enabled.is_(True),
                )
                .limit(1)
            )
            has_slo = db.scalar(
                select(SLO.id)
                .where(
                    SLO.organization_id == project.organization_id,
                    SLO.project_id == project.id,
                    SLO.enabled.is_(True),
                )
                .limit(1)
            )
            if has_rule or has_slo:
                pending = db.scalar(
                    select(Job.id)
                    .where(
                        Job.organization_id == project.organization_id,
                        Job.project_id == project.id,
                        Job.kind == "detect",
                        Job.status.in_(["QUEUED", "RUNNING"]),
                    )
                    .limit(1)
                )
                if not pending:
                    db.add(
                        Job(
                            organization_id=project.organization_id,
                            project_id=project.id,
                            kind="detect",
                            resource_id=f"tick-{minute}",
                        )
                    )
            retain_project(db, project)
