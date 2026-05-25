"""issue 448 database integrity hardening

Revision ID: 0034_issue_448_integrity_hardening
Revises: 0033_revoke_unused_fn_grants
Create Date: 2026-05-25
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0034_issue_448_integrity_hardening"
down_revision: str | None = "0033_revoke_unused_fn_grants"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_DROP_RESULT_SUBMISSION_FK = """
DO $$
DECLARE
    existing_constraint_name text;
BEGIN
    SELECT constraint_row.conname
    INTO existing_constraint_name
    FROM pg_constraint constraint_row
    JOIN pg_class source_table
        ON source_table.oid = constraint_row.conrelid
    JOIN pg_class target_table
        ON target_table.oid = constraint_row.confrelid
    JOIN pg_attribute source_column
        ON source_column.attrelid = source_table.oid
        AND source_column.attnum = ANY(constraint_row.conkey)
    WHERE source_table.relname = 'verification_jobs'
        AND target_table.relname = 'submissions'
        AND source_column.attname = 'result_submission_id'
        AND constraint_row.contype = 'f'
    LIMIT 1;

    IF existing_constraint_name IS NOT NULL THEN
        EXECUTE format(
            'ALTER TABLE verification_jobs DROP CONSTRAINT %I',
            existing_constraint_name
        );
    END IF;
END $$;
"""


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '2min'")

    op.execute("CREATE EXTENSION IF NOT EXISTS pg_stat_statements")

    op.execute(
        """
        UPDATE submissions
        SET validated_at = COALESCE(updated_at, created_at)
        WHERE is_validated IS TRUE
            AND validated_at IS NULL
        """
    )
    op.execute(
        """
        UPDATE submissions
        SET verification_completed = TRUE
        WHERE is_validated IS TRUE
            AND verification_completed IS NOT TRUE
        """
    )
    op.execute(
        """
        ALTER TABLE submissions
            ADD CONSTRAINT ck_submissions_validated_at_when_validated
            CHECK (is_validated IS FALSE OR validated_at IS NOT NULL)
            NOT VALID
        """
    )
    op.execute(
        """
        ALTER TABLE submissions
            ADD CONSTRAINT ck_submissions_completed_when_validated
            CHECK (is_validated IS FALSE OR verification_completed IS TRUE)
            NOT VALID
        """
    )

    op.execute(_DROP_RESULT_SUBMISSION_FK)
    op.execute(
        """
        ALTER TABLE verification_jobs
            ADD CONSTRAINT fk_verification_jobs_result_submission_id
            FOREIGN KEY (result_submission_id) REFERENCES submissions(id)
            NOT VALID
        """
    )


def downgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '2min'")

    op.execute(_DROP_RESULT_SUBMISSION_FK)
    op.execute(
        """
        ALTER TABLE verification_jobs
            ADD CONSTRAINT verification_jobs_result_submission_id_fkey
            FOREIGN KEY (result_submission_id) REFERENCES submissions(id)
            ON DELETE SET NULL
            NOT VALID
        """
    )

    op.execute(
        """
        ALTER TABLE submissions
            DROP CONSTRAINT IF EXISTS
            ck_submissions_completed_when_validated
        """
    )
    op.execute(
        """
        ALTER TABLE submissions
            DROP CONSTRAINT IF EXISTS
            ck_submissions_validated_at_when_validated
        """
    )
