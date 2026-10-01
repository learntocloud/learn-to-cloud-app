"""Add active-job indexes keyed on result_submission_id.

PR3 expand step. Application code switches to ``result_submission_id IS NULL``
as the "active verification job" predicate; this revision adds the supporting
indexes alongside the existing status-based ones so both old and new code
paths work during the rolling deploy. A future migration will drop the old
``status``-based index and column once all pods have moved to the new code.

Revision ID: 0020_add_result_submission_id_indexes
Revises: 0019_enforce_not_null_columns
Create Date: 2026-05-20
"""

from __future__ import annotations

from alembic import op

revision = "0020_add_result_submission_id_indexes"
down_revision = "0019_enforce_not_null_columns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Clean up ghost rows that would violate the new partial unique index.
    # These are verification jobs with a terminal status but no linked
    # submission (result_submission_id IS NULL). Without this DELETE,
    # create_index below fails on databases with real data because
    # multiple terminal jobs for the same (user_id, requirement_id)
    # all satisfy the WHERE clause. See incident #432.
    op.execute(
        "DELETE FROM verification_jobs "
        "WHERE result_submission_id IS NULL "
        "AND status IN ("
        "'succeeded', 'failed', 'server_error', 'cancelled'"
        ")"
    )

    # New partial unique index: replaces the role of
    # ``uq_verification_jobs_active_user_requirement`` (status-based) once
    # all pods are on the new code. Kept additive in this revision so old
    # pods running PR2 code can keep using the status-based predicate.
    op.create_index(
        "uq_verification_jobs_active_user_requirement_v2",
        "verification_jobs",
        ["user_id", "requirement_id"],
        unique=True,
        postgresql_where="result_submission_id IS NULL",
    )
    # Supporting (non-unique) index for ``get_active_for_phase`` queries
    # under the new predicate.
    op.create_index(
        "ix_verification_jobs_user_phase_active",
        "verification_jobs",
        ["user_id", "phase_id"],
        unique=False,
        postgresql_where="result_submission_id IS NULL",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_verification_jobs_user_phase_active",
        table_name="verification_jobs",
    )
    op.drop_index(
        "uq_verification_jobs_active_user_requirement_v2",
        table_name="verification_jobs",
    )
