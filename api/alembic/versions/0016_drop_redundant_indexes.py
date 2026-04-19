"""Drop redundant submission indexes.

Revision ID: 0006
Revises: 0005
Create Date: 2025-07-18

Removes 3 overlapping indexes on the submissions table:
- ix_submissions_user_phase_validated (partial index, covered by user_phase_req)
- ix_submissions_user_updated_at (no query uses just user_id + updated_at)
- ix_submissions_user_req_verified_updated (over-specific, covered by user_req_latest)
"""

from alembic import op

revision = "0016_drop_redundant_indexes"
down_revision = "0015_add_ci_status_submission_type"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("ix_submissions_user_phase_validated", table_name="submissions")
    op.drop_index("ix_submissions_user_updated_at", table_name="submissions")
    op.drop_index("ix_submissions_user_req_verified_updated", table_name="submissions")


def downgrade() -> None:
    op.create_index(
        "ix_submissions_user_req_verified_updated",
        "submissions",
        ["user_id", "requirement_id", "verification_completed", "updated_at"],
    )
    op.create_index(
        "ix_submissions_user_updated_at",
        "submissions",
        ["user_id", "updated_at"],
    )
    # Partial index — PostgreSQL-specific
    op.create_index(
        "ix_submissions_user_phase_validated",
        "submissions",
        ["user_id", "phase_id"],
        postgresql_where="is_validated",
    )
