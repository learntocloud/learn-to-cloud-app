"""Add covering indexes for submission queries.

Revision ID: 0005_submission_covering_indexes
Revises: 0004_analytics_snapshot_and_indexes
Create Date: 2026-02-09
"""

from alembic import op

revision = "0005_submission_covering_indexes"
down_revision = "0004_analytics_snapshot_and_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_submissions_user_verified_updated",
        "submissions",
        ["user_id", "verification_completed", "updated_at"],
    )
    op.create_index(
        "ix_submissions_user_req_verified_updated",
        "submissions",
        ["user_id", "requirement_id", "verification_completed", "updated_at"],
    )
    op.create_index(
        "ix_submissions_user_phase_req",
        "submissions",
        ["user_id", "phase_id", "requirement_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_submissions_user_phase_req", table_name="submissions")
    op.drop_index("ix_submissions_user_req_verified_updated", table_name="submissions")
    op.drop_index("ix_submissions_user_verified_updated", table_name="submissions")
