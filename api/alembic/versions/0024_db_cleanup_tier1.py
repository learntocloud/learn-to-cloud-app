"""Tier 1 DB cleanup: drop redundant indexes and unused user_phase_progress.

Three subtractive changes that remove pure dead weight:

* ``ix_submissions_user_phase`` is fully covered by the wider
  ``ix_submissions_user_phase_req`` index added later.
* ``ix_step_progress_completed_at`` has no queries that filter by
  ``completed_at`` alone; the index has not been used by any code path
  since at least the htmx baseline.
* ``user_phase_progress`` is denormalized state that the runtime app
  no longer reads. ``progress_service.fetch_user_progress`` derives
  validated counts live from the ``submissions`` table. The only
  remaining writers are operational reset runbooks, which are updated
  in the same change to stop touching the table.

Revision ID: 0024_db_cleanup_tier1
Revises: 0023_rename_ci_status_submission_type
Create Date: 2026-05-23
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0024_db_cleanup_tier1"
down_revision = "0023_rename_ci_status_submission_type"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("ix_submissions_user_phase", table_name="submissions")
    op.drop_index("ix_step_progress_completed_at", table_name="step_progress")
    op.drop_index("ix_user_phase_progress_user", table_name="user_phase_progress")
    op.drop_table("user_phase_progress")


def downgrade() -> None:
    op.create_table(
        "user_phase_progress",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("phase_id", sa.Integer(), nullable=False),
        sa.Column(
            "validated_submissions",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "phase_id", name="uq_user_phase_progress"),
    )
    op.create_index("ix_user_phase_progress_user", "user_phase_progress", ["user_id"])
    op.execute(
        """
        INSERT INTO user_phase_progress
            (user_id, phase_id, validated_submissions, updated_at)
        SELECT
            user_id,
            phase_id,
            COUNT(DISTINCT requirement_id) AS validated_submissions,
            NOW()
        FROM submissions
        WHERE is_validated = true
        GROUP BY user_id, phase_id
        """
    )

    op.create_index("ix_step_progress_completed_at", "step_progress", ["completed_at"])
    op.create_index("ix_submissions_user_phase", "submissions", ["user_id", "phase_id"])
