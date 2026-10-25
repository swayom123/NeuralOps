import logging
import time
from datetime import timedelta

from sqlalchemy import and_, or_, select, text

from .db import SessionLocal, ensure_runtime_role
from .domain import detect, evaluate, persist_diagnosis, reconstruct
from .maintenance import schedule
from .models import Evaluation, Job, now

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("neuralops.worker")


def tick() -> bool:
    with SessionLocal.begin() as db:
        job = db.scalar(
            select(Job)
            .where(
                or_(
                    and_(Job.status == "QUEUED", Job.available_at <= now()),
                    and_(Job.status == "RUNNING", Job.lease_until <= now()),
                ),
                Job.attempts < 5,
            )
            .order_by(Job.available_at, Job.id)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if not job:
            return False
        job.status, job.lease_until, job.attempts = (
            "RUNNING",
            now() + timedelta(seconds=60),
            job.attempts + 1,
        )
        if job.kind == "evaluation":
            run = db.get(Evaluation, job.resource_id)
            if (
                run
                and run.organization_id == job.organization_id
                and run.project_id == job.project_id
                and run.status != "COMPLETED"
            ):
                run.status = "RUNNING"
        job_id, attempt = job.id, job.attempts
    try:
        with SessionLocal.begin() as db:
            job = db.scalar(select(Job).where(Job.id == job_id).with_for_update())
            if job.status != "RUNNING" or job.attempts != attempt:
                return True
            # Serializes processing per project: stable trace merges and bounded rule grouping.
            db.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:scope, 0))"),
                {"scope": f"{job.organization_id}:{job.project_id}"},
            )
            if job.kind == "trace":
                reconstruct(db, job)
                detect(db, job.organization_id, job.project_id)
            elif job.kind == "detect":
                detect(db, job.organization_id, job.project_id)
            elif job.kind == "evaluation":
                evaluate(db, job)
            elif job.kind == "diagnosis":
                persist_diagnosis(db, job)
            else:
                raise ValueError("UNKNOWN_JOB_KIND")
            job.status, job.lease_until, job.last_error = "COMPLETED", None, None
    except Exception:  # noqa: BLE001 — security/process boundary; redact error details
        logger.error("job_failed id=%s attempt=%s", job_id, attempt)
        with SessionLocal.begin() as db:
            job = db.get(Job, job_id)
            job.status = "DEAD_LETTER" if job.attempts >= 5 else "QUEUED"
            if job.status == "DEAD_LETTER" and job.kind == "evaluation":
                run = db.get(Evaluation, job.resource_id)
                if run and run.organization_id == job.organization_id and run.project_id == job.project_id:
                    run.status = "FAILED"
            job.available_at = now() + timedelta(seconds=min(60, 2**job.attempts))
            job.lease_until, job.last_error = None, "PROCESSING_FAILED"
    return True


if __name__ == "__main__":
    ensure_runtime_role("neuralops_worker")
    logger.info("Worker started; remote actions disabled")
    last_schedule = 0
    while True:
        try:
            if time.monotonic() - last_schedule >= 10:
                schedule()
                last_schedule = time.monotonic()
            if not tick():
                time.sleep(1)
        except KeyboardInterrupt:
            break
        except Exception:  # noqa: BLE001 — security/process boundary; redact error details
            logger.error("worker_database_unavailable")
            time.sleep(5)
