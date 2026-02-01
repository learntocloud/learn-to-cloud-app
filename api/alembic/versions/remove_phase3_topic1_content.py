"""remove phase3-topic1 references

Revision ID: remove_phase3_topic1
Revises: 5aba277e1361
Create Date: 2026-01-30

"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "remove_phase3_topic1"
down_revision = "5aba277e1361"
branch_labels = None
depends_on = None

_TOPIC_ID = "phase3-topic1"


def upgrade() -> None:
    """Remove progress and question attempts for the removed topic."""
    op.execute(
        sa.text("DELETE FROM question_attempts WHERE topic_id = :topic_id").bindparams(
            topic_id=_TOPIC_ID
        )
    )
    op.execute(
        sa.text("DELETE FROM step_progress WHERE topic_id = :topic_id").bindparams(
            topic_id=_TOPIC_ID
        )
    )


def downgrade() -> None:
    """No-op: deleted topic data cannot be restored."""
    return
