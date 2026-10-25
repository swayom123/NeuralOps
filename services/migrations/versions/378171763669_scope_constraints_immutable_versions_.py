"""Scope constraints, immutable rule versions and shared request quotas."""

import sqlalchemy as sa
from alembic import op

revision = "378171763669"
down_revision = "7503b5908513"
branch_labels = None
depends_on = None
SCOPED_TABLES = (
    "datasets",
    "evaluations",
    "incidents",
    "ingestion_credentials",
    "jobs",
    "remediations",
    "rules",
    "spans",
    "traces",
)
RESOURCE_REFS = (
    ("incidents", "rule_id", "rules"),
    ("evaluations", "dataset_id", "datasets"),
    ("remediations", "incident_id", "incidents"),
)


def upgrade():
    # Referenced unique constraints must exist before any composite foreign keys.
    op.create_unique_constraint("uq_project_scope", "projects", ["organization_id", "id"])
    for table in ("rules", "incidents", "datasets"):
        op.create_unique_constraint(f"uq_{table}_scope", table, ["organization_id", "project_id", "id"])
    op.create_table(
        "rate_buckets",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("minute", sa.BigInteger(), primary_key=True),
        sa.Column("count", sa.Integer(), nullable=False),
    )
    op.create_table(
        "rule_versions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("rule_id", sa.String(36), sa.ForeignKey("rules.id"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("manifest", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("rule_id", "version"),
        sa.ForeignKeyConstraint(
            ["organization_id", "project_id"],
            ["projects.organization_id", "projects.id"],
            name="fk_rule_versions_project_scope",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "project_id", "rule_id"],
            ["rules.organization_id", "rules.project_id", "rules.id"],
            name="fk_rule_versions_rules_scope",
        ),
    )
    for table in SCOPED_TABLES:
        op.create_foreign_key(
            f"fk_{table}_project_scope",
            table,
            "projects",
            ["organization_id", "project_id"],
            ["organization_id", "id"],
        )
    for table, field, target in RESOURCE_REFS:
        op.create_foreign_key(
            f"fk_{table}_{target}_scope",
            table,
            target,
            ["organization_id", "project_id", field],
            ["organization_id", "project_id", "id"],
        )


def downgrade():
    op.drop_table("rule_versions")
    op.drop_table("rate_buckets")
    for table, field, target in RESOURCE_REFS:
        op.drop_constraint(f"fk_{table}_{target}_scope", table, type_="foreignkey")
    for table in SCOPED_TABLES:
        op.drop_constraint(f"fk_{table}_project_scope", table, type_="foreignkey")
    for table in ("rules", "incidents", "datasets"):
        op.drop_constraint(f"uq_{table}_scope", table, type_="unique")
    op.drop_constraint("uq_project_scope", "projects", type_="unique")
