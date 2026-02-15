"""Drop unused completed_steps column from user_phase_progress.

Step completion counts are now computed live from step_progress rows
intersected with current content definitions. The denormalized
completed_steps column is no longer written or read.

Revision ID: 0013_drop_completed_steps_column
Revises: 0012_remove_iac_token_add_pr_review
Create Date: 2026-02-15
"""

import sqlalchemy as sa

from alembic import op

revision = "0013_drop_completed_steps_column"
down_revision = "039941763eac"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("user_phase_progress", "completed_steps")


def downgrade() -> None:
    op.add_column(
        "user_phase_progress",
        sa.Column(
            "completed_steps",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
    )
