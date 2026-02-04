"""drop user_phase_progress cache table

Progress is now computed directly from source tables (step_progress, submissions)
with in-memory caching. This eliminates drift bugs where cached counts get out
of sync with actual data.

Revision ID: drop_user_phase_progress
Revises: fix_phase_progress_drift
Create Date: 2026-02-04

"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "drop_user_phase_progress"
down_revision = "fix_phase_progress_drift"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("ix_user_phase_progress_user", table_name="user_phase_progress")
    op.drop_table("user_phase_progress")


def downgrade() -> None:
    op.create_table(
        "user_phase_progress",
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column("phase_id", sa.Integer(), nullable=False),
        sa.Column(
            "steps_completed",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "hands_on_validated_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "phase_id"),
    )
    op.create_index(
        "ix_user_phase_progress_user",
        "user_phase_progress",
        ["user_id"],
        unique=False,
    )
