"""fix phase progress drift from remove_phase3_topic1 migration

The remove_phase3_topic1 migration deleted step_progress records
but did not decrement user_phase_progress.steps_completed, causing
phantom progress to display in the UI.

This migration recalculates all user_phase_progress counts from the
actual source-of-truth tables (step_progress and submissions).

Revision ID: fix_phase_progress_drift
Revises: add_phase_id_progress, d8f4c1b2a9f0
Create Date: 2026-02-04

"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "fix_phase_progress_drift"
down_revision = ("add_phase_id_progress", "d8f4c1b2a9f0")
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Recalculate user_phase_progress from source-of-truth tables."""
    # Update steps_completed to match actual step_progress count per user/phase
    op.execute(
        sa.text(
            """
            UPDATE user_phase_progress upp
            SET steps_completed = COALESCE(actual.cnt, 0),
                updated_at = NOW()
            FROM (
                SELECT user_id, phase_id, COUNT(*) as cnt
                FROM step_progress
                GROUP BY user_id, phase_id
            ) actual
            WHERE upp.user_id = actual.user_id
              AND upp.phase_id = actual.phase_id
              AND upp.steps_completed != actual.cnt
            """
        )
    )

    # Set steps_completed to 0 for phases with no step_progress records
    op.execute(
        sa.text(
            """
            UPDATE user_phase_progress upp
            SET steps_completed = 0,
                updated_at = NOW()
            WHERE upp.steps_completed > 0
              AND NOT EXISTS (
                  SELECT 1 FROM step_progress sp
                  WHERE sp.user_id = upp.user_id
                    AND sp.phase_id = upp.phase_id
              )
            """
        )
    )

    # Update hands_on_validated_count to match actual validated submissions
    op.execute(
        sa.text(
            """
            UPDATE user_phase_progress upp
            SET hands_on_validated_count = COALESCE(actual.cnt, 0),
                updated_at = NOW()
            FROM (
                SELECT user_id, phase_id, COUNT(*) as cnt
                FROM submissions
                WHERE is_validated = true
                GROUP BY user_id, phase_id
            ) actual
            WHERE upp.user_id = actual.user_id
              AND upp.phase_id = actual.phase_id
              AND upp.hands_on_validated_count != actual.cnt
            """
        )
    )

    # Set hands_on_validated_count to 0 for phases with no validated submissions
    op.execute(
        sa.text(
            """
            UPDATE user_phase_progress upp
            SET hands_on_validated_count = 0,
                updated_at = NOW()
            WHERE upp.hands_on_validated_count > 0
              AND NOT EXISTS (
                  SELECT 1 FROM submissions s
                  WHERE s.user_id = upp.user_id
                    AND s.phase_id = upp.phase_id
                    AND s.is_validated = true
              )
            """
        )
    )


def downgrade() -> None:
    """No-op: this is a data repair, not a schema change."""
    pass
