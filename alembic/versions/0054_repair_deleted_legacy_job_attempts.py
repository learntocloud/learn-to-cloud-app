"""repair active attempts whose legacy jobs were already deleted

Why this change: migration 0053 protects future legacy job deletes, but an old
poller may have deleted a job between the original backfill and installation of
that trigger. Those attempts must not remain active and block retries.

Data effect:
- Compare-and-sets active legacy-provenance attempts with no remaining job to
  ``server_error``.

Rollback preserves repaired terminal outcomes.

Revision ID: 0054_repair_deleted_legacy_job_attempts
Revises: 0053_bridge_legacy_job_deletes
Create Date: 2026-07-14
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0054_repair_deleted_legacy_job_attempts"
down_revision: str | None = "0053_bridge_legacy_job_deletes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '5min'")

    op.execute(
        """
        UPDATE verification_attempts AS a
        SET outcome = 'server_error',
            started_at = COALESCE(a.started_at, a.created_at),
            completed_at = now(),
            validation_message =
                'Legacy verification ended before recording a result.',
            error_code = 'server_error',
            terminal_source = 'legacy_job_repair',
            updated_at = now()
        WHERE a.outcome IS NULL
          AND a.legacy_job_id IS NOT NULL
          AND NOT EXISTS (
            SELECT 1
            FROM verification_jobs vj
            WHERE vj.id = a.legacy_job_id
          )
        """
    )


def downgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '30s'")
