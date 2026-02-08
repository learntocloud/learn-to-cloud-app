"""add analytics_snapshot table and missing indexes

Revision ID: 0004_analytics_snapshot_and_indexes
Revises: 0003_drop_certificate_type
Create Date: 2026-02-08

Adds:
- analytics_snapshot table for pre-computed analytics (background refresh)
- Index on step_progress.completed_at (analytics + active learners queries)
- Index on submissions(user_id, updated_at) (daily submission cap hot path)
"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "0004_analytics_snapshot_and_indexes"
down_revision = "0003_drop_certificate_type"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -- Widen alembic_version.version_num (default varchar(32) is too short) --
    # This revision ID is 40 chars; must widen BEFORE Alembic stamps the version.
    op.execute(
        "ALTER TABLE alembic_version " "ALTER COLUMN version_num TYPE varchar(128)"
    )

    # -- Analytics snapshot table (single-row, stores pre-computed JSON) --
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

    # -- Missing indexes for query performance --
    # Used by: get_active_learners(30), get_activity_by_day_of_week()
    op.create_index(
        "ix_step_progress_completed_at",
        "step_progress",
        ["completed_at"],
    )

    # Used by: count_submissions_today() — hot path on every submission
    op.create_index(
        "ix_submissions_user_updated_at",
        "submissions",
        ["user_id", "updated_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_submissions_user_updated_at", table_name="submissions")
    op.drop_index("ix_step_progress_completed_at", table_name="step_progress")
    op.drop_table("analytics_snapshot")
