"""Add cloud_provider column to submissions.

Tracks which cloud provider (aws, azure, gcp) was used for
multi-cloud lab submissions (e.g. networking lab).  Nullable
because most submission types are provider-agnostic.

Revision ID: 0009_add_cloud_provider
Revises: 0008_add_validation_message
Create Date: 2026-02-12
"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "0009_add_cloud_provider"
down_revision = "0008_add_validation_message"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "submissions",
        sa.Column("cloud_provider", sa.String(16), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("submissions", "cloud_provider")
