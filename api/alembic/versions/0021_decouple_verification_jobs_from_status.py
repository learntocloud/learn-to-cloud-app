"""Decouple verification_jobs from the legacy status columns.

PR4 of the verification-job slim-down: application code stops referencing
``status`` and the other lifecycle columns. The columns themselves stay in
the DB so PR3 pods can still ``SELECT *`` them during the rolling deploy;
a future PR5 will drop them along with the ``verification_job_status``
enum type.

This revision performs three small additive changes:

1. Add a server-side DEFAULT of ``'queued'`` to ``status``. After PR4 the
   SQLAlchemy model no longer includes ``status`` so INSERTs would
   otherwise violate the ``NOT NULL`` constraint.
2. Drop two now-unused legacy indexes:

   - ``ix_verification_jobs_status_updated`` (no PR3+ code queries by
     ``status``).
   - ``uq_verification_jobs_active_user_requirement`` (PR3+ code uses
     the ``result_submission_id IS NULL`` partial unique index instead).

3. One-off cleanup: delete any "ghost" rows where the legacy status is
   terminal but no ``Submission`` was linked. The only pre-PR2 path that
   could create such a row was ``_mark_missing_requirement`` in the
   executor; PR2 removed that pattern. The DELETE is defensive and
   keeps the new ``result_submission_id IS NULL`` partial unique index
   from refusing legitimate submits because of a stale leftover.

Revision ID: 0021_decouple_verification_jobs_from_status
Revises: 0020_add_result_submission_id_indexes
Create Date: 2026-05-20
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0021_decouple_verification_jobs_from_status"
down_revision = "0020_add_result_submission_id_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE verification_jobs ALTER COLUMN status SET DEFAULT 'queued'")
    op.drop_index(
        "ix_verification_jobs_status_updated",
        table_name="verification_jobs",
    )
    op.drop_index(
        "uq_verification_jobs_active_user_requirement",
        table_name="verification_jobs",
    )
    op.execute(
        sa.text(
            "DELETE FROM verification_jobs "
            "WHERE result_submission_id IS NULL "
            "AND status IN ('succeeded', 'failed', 'server_error', 'cancelled')"
        )
    )


def downgrade() -> None:
    op.create_index(
        "uq_verification_jobs_active_user_requirement",
        "verification_jobs",
        ["user_id", "requirement_id"],
        unique=True,
        postgresql_where="status IN ('queued', 'starting', 'running')",
    )
    op.create_index(
        "ix_verification_jobs_status_updated",
        "verification_jobs",
        ["status", "updated_at"],
    )
    op.execute("ALTER TABLE verification_jobs ALTER COLUMN status DROP DEFAULT")
