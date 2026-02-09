"""Add denormalized user_phase_progress table.

Revision ID: 0006_user_phase_progress
Revises: 0005_submission_covering_indexes
Create Date: 2026-02-10
"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "0006_user_phase_progress"
down_revision = "0005_submission_covering_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_phase_progress",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("phase_id", sa.Integer(), nullable=False),
        sa.Column("completed_steps", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "validated_submissions", sa.Integer(), server_default="0", nullable=False
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "phase_id", name="uq_user_phase_progress"),
    )
    op.create_index("ix_user_phase_progress_user", "user_phase_progress", ["user_id"])

    # Backfill from existing data
    op.execute(
        """
        INSERT INTO user_phase_progress
            (user_id, phase_id, completed_steps,
             validated_submissions, updated_at)
        SELECT
            COALESCE(s.user_id, p.user_id) as user_id,
            COALESCE(s.phase_id, p.phase_id) as phase_id,
            COALESCE(p.step_count, 0) as completed_steps,
            COALESCE(s.sub_count, 0) as validated_submissions,
            NOW()
        FROM (
            SELECT user_id, phase_id, COUNT(DISTINCT requirement_id) as sub_count
            FROM submissions WHERE is_validated = true
            GROUP BY user_id, phase_id
        ) s
        FULL OUTER JOIN (
            SELECT user_id, phase_id, COUNT(*) as step_count
            FROM step_progress
            GROUP BY user_id, phase_id
        ) p ON s.user_id = p.user_id AND s.phase_id = p.phase_id
    """
    )


def downgrade() -> None:
    op.drop_index("ix_user_phase_progress_user", table_name="user_phase_progress")
    op.drop_table("user_phase_progress")
