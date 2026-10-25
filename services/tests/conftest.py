"""Integration tests use a separate PostgreSQL database, never the development database."""

import os
import secrets
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from dotenv import dotenv_values
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool

root = Path(__file__).resolve().parents[2]
config = dotenv_values(root / ".env")
url = make_url(os.environ.get("TEST_DATABASE_URL") or config["DATABASE_URL"]).set(database="neuralops_test")
admin_url = url.set(database="postgres")
admin = create_engine(admin_url, isolation_level="AUTOCOMMIT", poolclass=NullPool)
with admin.connect() as conn:
    if not conn.scalar(text("SELECT 1 FROM pg_database WHERE datname='neuralops_test'")):
        conn.execute(text("CREATE DATABASE neuralops_test"))
admin.dispose()
os.environ.update(
    DATABASE_URL=url.render_as_string(hide_password=False),
    ENVIRONMENT="test",
    DEV_AUTH="true",
    SESSION_SECRET=secrets.token_urlsafe(48),
    PUBLIC_ORIGIN="http://localhost:3000",
)

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from neuralops.api import app  # noqa: E402
from neuralops.db import SessionLocal  # noqa: E402
from neuralops.models import Membership, Organization, Project, UserSession, now  # noqa: E402
from neuralops.security import digest  # noqa: E402
from neuralops.telemetry import app as collector  # noqa: E402

alembic_config = Config(str(root / "services/alembic.ini"))
alembic_config.set_main_option("script_location", str(root / "services/migrations"))
command.upgrade(alembic_config, "head")
from neuralops.db import engine  # noqa: E402

with engine.begin() as connection:
    connection.connection.driver_connection.execute((root / "infra/runtime-roles.sql").read_text())


@pytest.fixture
def identity():
    def create(role="admin", organization_id=None, project_id=None, project_ids=None):
        unique = uuid4().hex
        with SessionLocal.begin() as db:
            if organization_id is None:
                org = Organization(name=f"Test {unique}", slug=f"test-{unique}")
                db.add(org)
                db.flush()
                organization_id = org.id
            if project_id is None:
                project = Project(
                    organization_id=organization_id,
                    name="Synthetic fixture",
                    slug=f"fixture-{unique}",
                    environment="development",
                )
                db.add(project)
                db.flush()
                project_id = project.id
            member = Membership(
                organization_id=organization_id,
                subject=f"test-{unique}",
                name=f"User {role}",
                role=role,
                project_ids=[project_id] if project_ids is None else project_ids,
            )
            db.add(member)
            db.flush()
            token, csrf = secrets.token_urlsafe(48), secrets.token_urlsafe(32)
            db.add(
                UserSession(
                    id=digest(token),
                    membership_id=member.id,
                    csrf_hash=digest(csrf),
                    expires_at=now() + timedelta(hours=1),
                )
            )
            membership_id = member.id
        client = TestClient(app)
        client.cookies.set("neuralops_session", token)
        client.cookies.set("neuralops_csrf", csrf)
        client.headers.update({"Origin": "http://localhost:3000", "X-CSRF-Token": csrf})
        return client, project_id, organization_id, membership_id

    return create


@pytest.fixture
def gateway():
    return TestClient(collector)
