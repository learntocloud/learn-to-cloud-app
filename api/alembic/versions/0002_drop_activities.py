"""drop user_activities table

Revision ID: 0002_drop_activities
Revises: 0001_baseline
Create Date: 2026-02-07

Remove the user_activities table. Streak/activity tracking is no longer used.
"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "0002_drop_activities"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("ix_user_activities_user_type", table_name="user_activities")
    op.drop_index("ix_user_activities_user_date", table_name="user_activities")
    op.drop_table("user_activities")


def downgrade() -> None:
    op.create_table(
        "user_activities",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("activity_type", sa.String(50), nullable=False),
        sa.Column("activity_date", sa.Date(), nullable=False),
        sa.Column("reference_id", sa.String(100), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_user_activities_user_date",
        "user_activities",
        ["user_id", "activity_date"],
    )
    op.create_index(
        "ix_user_activities_user_type",
        "user_activities",
        ["user_id", "activity_type"],
    )
