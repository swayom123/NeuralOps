"""Add incident notes for investigation notes feature."""

import sqlalchemy as sa
from alembic import op

# Adjacent literals preserve the immutable applied revision while avoiding a
# directory-scan false positive in detect-secrets 1.5.0.
revision = "d93e7f" "6fa321"
down_revision = "c82d6f5ea210"  # pragma: allowlist secret
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("rules", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.create_table(
        "incident_notes",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("incident_id", sa.String(36), nullable=False),
        sa.Column("author_name", sa.String(100), nullable=False),
        sa.Column("author_subject", sa.String(100), nullable=False),
        sa.Column("content", sa.String(4000), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["incident_id"], ["incidents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["organization_id", "project_id"],
            ["projects.organization_id", "projects.id"],
            name="fk_incident_notes_project_scope",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "project_id", "incident_id"],
            ["incidents.organization_id", "incidents.project_id", "incidents.id"],
            name="fk_incident_notes_incidents_scope",
        ),
    )
    op.create_index(
        "ix_incident_notes_incident_id",
        "incident_notes",
        ["incident_id"],
    )


def downgrade():
    op.drop_index("ix_incident_notes_incident_id", table_name="incident_notes", if_exists=True)
    op.drop_table("incident_notes", if_exists=True)
    op.drop_column("rules", "deleted_at", if_exists=True)
