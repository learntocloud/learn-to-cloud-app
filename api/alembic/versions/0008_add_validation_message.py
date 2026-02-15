"""Add validation_message column to submissions.

Stores the user-facing validation error message so it persists across
page reloads and app restarts.  Previously, non-task-result feedback
(e.g. deployed API errors) was lost on reload.

Revision ID: 0008_add_validation_message
Revises: 0007_submission_attempt_history
Create Date: 2026-02-09
"""

import sqlalchemy as sa

from alembic import op

revision = "0008_add_validation_message"
down_revision = "0007_submission_attempt_history"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "submissions",
        sa.Column("validation_message", sa.String(1024), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("submissions", "validation_message")
