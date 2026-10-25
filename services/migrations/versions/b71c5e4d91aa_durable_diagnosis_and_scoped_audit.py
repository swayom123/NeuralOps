"""Persist diagnosis evidence and scope audit events to projects."""

import sqlalchemy as sa
from alembic import op

revision = "b71c5e4d91aa"  # pragma: allowlist secret — Alembic revision identifier.
down_revision = "a450f51177c5"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("audit_events", sa.Column("project_id", sa.String(36), nullable=True))
    op.create_index("ix_audit_events_project_id", "audit_events", ["project_id"])
    op.create_foreign_key(
        "fk_audit_events_project_scope",
        "audit_events",
        "projects",
        ["organization_id", "project_id"],
        ["organization_id", "id"],
    )
    op.create_table(
        "hypotheses",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("incident_id", sa.String(36), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(180), nullable=False),
        sa.Column("evidence_class", sa.String(24), nullable=False),
        sa.Column("algorithm", sa.String(64), nullable=False),
        sa.Column("summary", sa.String(500), nullable=False),
        sa.Column("counterevidence", sa.String(500), nullable=False),
        sa.Column("missing", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("incident_id", "rank"),
        sa.UniqueConstraint("organization_id", "project_id", "id", name="uq_hypotheses_scope"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["incident_id"], ["incidents.id"]),
        sa.ForeignKeyConstraint(
            ["organization_id", "project_id"],
            ["projects.organization_id", "projects.id"],
            name="fk_hypotheses_project_scope",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "project_id", "incident_id"],
            ["incidents.organization_id", "incidents.project_id", "incidents.id"],
            name="fk_hypotheses_incidents_scope",
        ),
    )
    op.create_index("ix_hypotheses_incident_id", "hypotheses", ["incident_id"])
    op.create_table(
        "evidence_links",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("hypothesis_id", sa.String(36), nullable=False),
        sa.Column("trace_id", sa.String(32), nullable=False),
        sa.Column("span_id", sa.String(16), nullable=False),
        sa.Column("operation", sa.String(128), nullable=False),
        sa.UniqueConstraint("hypothesis_id", "trace_id", "span_id"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["hypothesis_id"], ["hypotheses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["organization_id", "project_id"],
            ["projects.organization_id", "projects.id"],
            name="fk_evidence_links_project_scope",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "project_id", "hypothesis_id"],
            ["hypotheses.organization_id", "hypotheses.project_id", "hypotheses.id"],
            name="fk_evidence_links_hypotheses_scope",
        ),
    )
    op.create_index("ix_evidence_links_hypothesis_id", "evidence_links", ["hypothesis_id"])
    # Existing incidents enter the same bounded worker path as newly detected incidents.
    op.execute(
        """INSERT INTO jobs (id, organization_id, project_id, kind, resource_id, status,
                              attempts, available_at, lease_until, last_error)
           SELECT gen_random_uuid()::text, organization_id, project_id, 'diagnosis', id,
                  'QUEUED', 0, now(), NULL, NULL FROM incidents"""
    )


def downgrade():
    op.execute("DELETE FROM jobs WHERE kind='diagnosis'")
    op.drop_index("ix_evidence_links_hypothesis_id", table_name="evidence_links")
    op.drop_table("evidence_links")
    op.drop_index("ix_hypotheses_incident_id", table_name="hypotheses")
    op.drop_table("hypotheses")
    op.drop_constraint("fk_audit_events_project_scope", "audit_events", type_="foreignkey")
    op.drop_index("ix_audit_events_project_id", table_name="audit_events")
    op.drop_column("audit_events", "project_id")
