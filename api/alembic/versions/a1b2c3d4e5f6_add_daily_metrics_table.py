"""add_daily_metrics_table

Revision ID: c7d8e9f0a1b2
Revises: remove_phase3_topic1
Create Date: 2026-01-30 12:00:00.000000

"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "c7d8e9f0a1b2"
down_revision = "remove_phase3_topic1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "daily_metrics",
        sa.Column("date", sa.Date(), nullable=False),
        # User engagement
        sa.Column("active_users", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("new_signups", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("returning_users", sa.Integer(), nullable=False, server_default="0"),
        # Learning progress
        sa.Column("steps_completed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "questions_attempted", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("questions_passed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "hands_on_submitted", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "hands_on_validated", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("phases_completed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "certificates_earned", sa.Integer(), nullable=False, server_default="0"
        ),
        # Computed metrics
        sa.Column(
            "question_pass_rate", sa.Float(), nullable=False, server_default="0.0"
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("date"),
    )


def downgrade() -> None:
    op.drop_table("daily_metrics")
