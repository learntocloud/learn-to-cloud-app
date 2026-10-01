"""drop orphaned analytics_snapshot table

Revision ID: 0018_drop_analytics_snapshot
Revises: 0017_add_verification_jobs
Create Date: 2026-05-08

The AnalyticsSnapshot model was removed from the codebase, but the table was
never dropped from the database. No code references the table anymore.
"""

import sqlalchemy as sa

from alembic import op

revision = "0018_drop_analytics_snapshot"
down_revision = "0017_add_verification_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("analytics_snapshot")


def downgrade() -> None:
    op.create_table(
        "analytics_snapshot",
        sa.Column("id", sa.Integer, primary_key=True, default=1),
        sa.Column("data", sa.Text, nullable=False),
        sa.Column(
            "computed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint("id = 1", name="ck_analytics_snapshot_single_row"),
    )
