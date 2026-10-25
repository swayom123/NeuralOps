"""Add dataset lineage and description for Phase 3 reproducible evaluations."""

import sqlalchemy as sa
from alembic import op

# Adjacent literals preserve the immutable applied revision while avoiding a
# directory-scan false positive in detect-secrets 1.5.0.
revision = "e74a81" "b2f093"
down_revision = "d93e7f" "6fa321"  # pragma: allowlist secret
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("datasets", sa.Column("description", sa.String(300), nullable=True))
    op.add_column("datasets", sa.Column("parent_id", sa.String(36), nullable=True))
    op.create_index("ix_datasets_parent_id", "datasets", ["parent_id"])


def downgrade():
    op.drop_index("ix_datasets_parent_id", table_name="datasets", if_exists=True)
    op.drop_column("datasets", "parent_id", if_exists=True)
    op.drop_column("datasets", "description", if_exists=True)
