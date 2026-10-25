"""Enforce scoped dataset lineage, unique versions and append-only incident notes."""

import sqlalchemy as sa
from alembic import op

revision = "f19a2b3c4d50"  # pragma: allowlist secret — public Alembic revision
down_revision = "e74a81b2f093"  # pragma: allowlist secret — public Alembic revision
branch_labels = None
depends_on = None


def upgrade():
    op.create_foreign_key(
        "fk_datasets_datasets_scope",
        "datasets",
        "datasets",
        ["organization_id", "project_id", "parent_id"],
        ["organization_id", "project_id", "id"],
    )
    op.create_check_constraint(
        "ck_dataset_lineage_version",
        "datasets",
        "(parent_id IS NULL AND version = 1) OR (parent_id IS NOT NULL AND version > 1)",
    )
    op.create_index(
        "uq_dataset_lineage_version",
        "datasets",
        ["organization_id", "project_id", sa.text("coalesce(parent_id, id)"), "version"],
        unique=True,
    )
    op.execute("""CREATE TRIGGER incident_notes_immutable BEFORE UPDATE OR DELETE ON incident_notes
                  FOR EACH ROW EXECUTE FUNCTION neuralops_immutable_record()""")


def downgrade():
    op.execute("DROP TRIGGER incident_notes_immutable ON incident_notes")
    op.drop_index("uq_dataset_lineage_version", table_name="datasets")
    op.drop_constraint("ck_dataset_lineage_version", "datasets", type_="check")
    op.drop_constraint("fk_datasets_datasets_scope", "datasets", type_="foreignkey")
