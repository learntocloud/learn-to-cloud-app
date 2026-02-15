"""Use stable step_id identity for step progress.

Revision ID: 0010_step_progress_step_id_identity
Revises: 0009_add_cloud_provider
Create Date: 2026-02-13
"""

import sqlalchemy as sa

from alembic import op

revision = "0010_step_progress_step_id_identity"
down_revision = "0009_add_cloud_provider"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("step_progress", sa.Column("step_id", sa.String(255), nullable=True))

    op.execute(
        """
        UPDATE step_progress
        SET step_id = topic_id || '-step-' || step_order::text
        WHERE step_id IS NULL
        """
    )

    op.alter_column("step_progress", "step_id", nullable=False)

    op.drop_constraint("uq_user_topic_step", "step_progress", type_="unique")
    op.create_unique_constraint(
        "uq_user_topic_step",
        "step_progress",
        ["user_id", "topic_id", "step_id"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_user_topic_step", "step_progress", type_="unique")
    op.create_unique_constraint(
        "uq_user_topic_step",
        "step_progress",
        ["user_id", "topic_id", "step_order"],
    )
    op.drop_column("step_progress", "step_id")
