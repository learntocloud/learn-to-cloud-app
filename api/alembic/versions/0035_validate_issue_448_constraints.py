"""validate issue 448 database constraints

Revision ID: 0035_validate_issue_448_constraints
Revises: 0034_issue_448_integrity_hardening
Create Date: 2026-05-25
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0035_validate_issue_448_constraints"
down_revision: str | None = "0034_issue_448_integrity_hardening"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '2min'")

    op.execute(
        """
        ALTER TABLE submissions
            VALIDATE CONSTRAINT ck_submissions_validated_at_when_validated
        """
    )
    op.execute(
        """
        ALTER TABLE submissions
            VALIDATE CONSTRAINT ck_submissions_completed_when_validated
        """
    )
    op.execute(
        """
        ALTER TABLE verification_jobs
            VALIDATE CONSTRAINT fk_verification_jobs_result_submission_id
        """
    )


def downgrade() -> None:
    pass
