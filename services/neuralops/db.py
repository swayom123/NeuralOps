from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import settings


class Base(DeclarativeBase):
    pass


engine = create_engine(
    settings().database_url,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=10,
    connect_args={"options": "-c statement_timeout=10000"},
)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def database():
    with SessionLocal() as db:
        yield db


def ready():
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))


def audit(
    db: Session,
    org: str,
    actor: str,
    action: str,
    target: str,
    request_id: str = "",
    outcome: str = "success",
    project_id: str | None = None,
):
    from .models import AuditEvent

    db.add(
        AuditEvent(
            organization_id=org,
            project_id=project_id,
            actor=actor,
            action=action,
            target=target,
            request_id=request_id,
            outcome=outcome,
        )
    )


def set_tenant(db: Session, organization_id: str):
    db.execute(
        text("SELECT set_config('neuralops.organization_id', :organization, true)"),
        {"organization": organization_id},
    )


def ensure_runtime_role(role: str):
    """Production fails closed on owner/superuser accounts or missing RLS policy deployment."""
    if settings().environment != "production":
        return
    expected = {"neuralops_api": "api", "neuralops_ingest": "ingest", "neuralops_worker": "worker"}
    if settings().runtime != expected[role]:
        raise RuntimeError("NEURALOPS_RUNTIME does not match the running service.")
    with engine.connect() as conn:
        valid = conn.scalar(
            text("""SELECT NOT r.rolsuper AND NOT r.rolbypassrls AND NOT r.rolcreaterole
                                    AND NOT r.rolcreatedb AND pg_has_role(current_user, :role, 'MEMBER')
                                    FROM pg_roles r WHERE r.rolname=current_user"""),
            {"role": role},
        )
        encrypted = conn.scalar(text("SELECT ssl FROM pg_stat_ssl WHERE pid=pg_backend_pid()"))
        other_roles = {"neuralops_api", "neuralops_ingest", "neuralops_worker"} - {role}
        overprivileged = any(
            conn.scalar(text("SELECT pg_has_role(current_user, :other, 'MEMBER')"), {"other": other})
            for other in other_roles
        )
        owns = conn.scalar(
            text(
                "SELECT EXISTS (SELECT 1 FROM pg_class WHERE relnamespace='public'::regnamespace AND pg_has_role(current_user,relowner,'USAGE'))"
            )
        )
        protected = conn.scalar(
            text(
                "SELECT count(*) FROM pg_class WHERE relnamespace='public'::regnamespace AND relname IN ('projects','spans','traces','jobs','incidents','hypotheses','evidence_links','incident_notes','detections','slos','slo_snapshots','change_events','evaluations','datasets','remediations','audit_events','ingestion_credentials','rules','rule_versions','expired_traces') AND relrowsecurity AND relforcerowsecurity"
            )
        )
        if not valid or owns or protected != 20 or overprivileged or not encrypted:
            raise RuntimeError(
                "Production requires encrypted DB transport, a dedicated runtime role and applied infra/runtime-roles.sql policies."
            )
