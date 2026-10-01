"""Store full submission attempt history instead of overwriting on retry.

Revision ID: 0007_submission_attempt_history
Revises: 0006_user_phase_progress
Create Date: 2026-02-15
"""

import sqlalchemy as sa

from alembic import op

revision = "0007_submission_attempt_history"
down_revision = "0006_user_phase_progress"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "submissions",
        sa.Column("attempt_number", sa.Integer(), nullable=False, server_default="1"),
    )

    op.execute("UPDATE submissions SET attempt_number = 1")
    op.drop_constraint("uq_user_requirement", "submissions", type_="unique")
    op.create_unique_constraint(
        "uq_user_requirement_attempt",
        "submissions",
        ["user_id", "requirement_id", "attempt_number"],
    )

    op.create_index(
        "ix_submissions_user_req_latest",
        "submissions",
        ["user_id", "requirement_id", sa.text("created_at DESC")],
    )


def downgrade() -> None:
    op.drop_index("ix_submissions_user_req_latest", table_name="submissions")
    op.drop_constraint("uq_user_requirement_attempt", "submissions", type_="unique")

    # Remove duplicate rows keeping only the latest attempt
    # per (user_id, requirement_id)
    op.execute(
        """
        DELETE FROM submissions
        WHERE id NOT IN (
            SELECT DISTINCT ON (user_id, requirement_id) id
            FROM submissions
            ORDER BY user_id, requirement_id, created_at DESC
        )
        """
    )

    op.create_unique_constraint(
        "uq_user_requirement", "submissions", ["user_id", "requirement_id"]
    )
    op.drop_column("submissions", "attempt_number")
