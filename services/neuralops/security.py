import hashlib
import hmac
import secrets
from datetime import timedelta
from typing import Annotated

from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from .config import settings
from .db import audit, database, set_tenant
from .models import Membership, Project, UserSession, now

DB = Annotated[Session, Depends(database)]


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def fail(status: int, code: str, message: str):
    raise HTTPException(status, detail={"code": code, "message": message})


def principal(request: Request, db: DB) -> Membership:
    token = request.cookies.get("neuralops_session", "")
    session = db.get(UserSession, digest(token)) if token else None
    if not session or session.expires_at <= now():
        fail(401, "UNAUTHENTICATED", "Sign in to continue.")
    member = db.get(Membership, session.membership_id)
    if not member:
        fail(401, "UNAUTHENTICATED", "Session is no longer valid.")
    request.state.actor = member.subject
    request.state.organization_id = member.organization_id
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        csrf = request.headers.get("x-csrf-token", "")
        if request.headers.get("origin") != settings().public_origin or not hmac.compare_digest(
            digest(csrf), session.csrf_hash
        ):
            fail(403, "CSRF_REJECTED", "Request origin or CSRF token is invalid.")
    consume_rate(f"api:{member.organization_id}", 600, db=db)
    set_tenant(db, member.organization_id)
    return member


Actor = Annotated[Membership, Depends(principal)]


def require(actor: Membership, *roles: str):
    if actor.role not in roles:
        fail(403, "FORBIDDEN", "Your role does not permit this operation.")


def project_scope(db: Session, actor: Membership, project_id: str) -> Project:
    project = db.get(Project, project_id)
    if not project or project.organization_id != actor.organization_id:
        fail(404, "NOT_FOUND", "Project not found.")
    if actor.role != "admin" and project.id not in actor.project_ids:
        fail(404, "NOT_FOUND", "Project not found.")
    return project


def scoped(db: Session, actor: Membership, model, identifier: str, project_id: str):
    project_scope(db, actor, project_id)
    obj = db.get(model, identifier)
    if (
        not obj
        or obj.organization_id != actor.organization_id
        or obj.project_id != project_id
        or (hasattr(obj, "deleted_at") and obj.deleted_at is not None)
    ):
        fail(404, "NOT_FOUND", "Resource not found.")
    return obj


def new_session(db: Session, member: Membership, response: Response, request_id: str):
    set_tenant(db, member.organization_id)
    token, csrf = secrets.token_urlsafe(48), secrets.token_urlsafe(32)
    db.add(
        UserSession(
            id=digest(token),
            membership_id=member.id,
            csrf_hash=digest(csrf),
            expires_at=now() + timedelta(hours=settings().session_hours),
        )
    )
    audit(
        db,
        member.organization_id,
        member.subject,
        "session.created",
        member.id,
        request_id,
    )
    secure = settings().environment == "production"
    response.set_cookie(
        "neuralops_session",
        token,
        httponly=True,
        secure=secure,
        samesite="lax",
        max_age=settings().session_hours * 3600,
        path="/",
    )
    response.set_cookie(
        "neuralops_csrf",
        csrf,
        httponly=False,
        secure=secure,
        samesite="strict",
        max_age=settings().session_hours * 3600,
        path="/",
    )


def consume_rate(key: str, maximum: int, db: Session | None = None):
    """Shared fixed window. Auth-only callers commit before domain mutations, releasing their connection."""
    import time

    from sqlalchemy.dialects.postgresql import insert

    from .db import SessionLocal
    from .models import RateBucket

    if db is None:
        with SessionLocal() as session:
            return consume_rate(key, maximum, db=session)
    statement = insert(RateBucket).values(key=digest(key), minute=int(time.time() // 60), count=1)
    count = db.scalar(
        statement.on_conflict_do_update(
            index_elements=["key", "minute"], set_={"count": RateBucket.count + 1}
        ).returning(RateBucket.count)
    )
    db.commit()
    if count > maximum:
        fail(429, "RATE_LIMITED", "Request quota exceeded. Retry next minute.")
