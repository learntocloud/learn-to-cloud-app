"""Add ci_status submission type, migrate code_analysis rows.

Replaces the LLM-based code_analysis verification for Phase 3 with a
CI status check.  Migrates any existing code_analysis submissions to
ci_status and removes code_analysis from the constraint.

Revision ID: 0015_add_ci_status_submission_type
Revises: 0014_drop_certificates_table
Create Date: 2026-04-10
"""

from alembic import op

revision = "0015_add_ci_status_submission_type"
down_revision = "0014_drop_certificates_table"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop old constraint first so the UPDATE doesn't violate it
    op.execute(
        """
        DO $$
        DECLARE
            constraint_name text;
        BEGIN
            FOR constraint_name IN
                SELECT conname
                FROM pg_constraint
                WHERE conrelid = 'submissions'::regclass
                  AND contype = 'c'
                  AND pg_get_constraintdef(oid) ILIKE '%submission_type%'
            LOOP
                EXECUTE format(
                    'ALTER TABLE submissions DROP CONSTRAINT %I',
                    constraint_name
                );
            END LOOP;
        END $$;
        """
    )
    # Migrate existing code_analysis rows to ci_status
    op.execute(
        "UPDATE submissions SET submission_type = 'ci_status' "
        "WHERE submission_type = 'code_analysis'"
    )
    op.create_check_constraint(
        "submission_type",
        "submissions",
        "submission_type IN ('github_profile', 'profile_readme', 'repo_fork', "
        "'ctf_token', 'networking_token', 'journal_api_response', "
        "'pr_review', 'ci_status', 'deployed_api', "
        "'devops_analysis', 'security_scanning')",
    )


def downgrade() -> None:
    # Restore code_analysis rows
    op.execute(
        "UPDATE submissions SET submission_type = 'code_analysis' "
        "WHERE submission_type = 'ci_status'"
    )
    op.execute(
        """
        DO $$
        DECLARE
            constraint_name text;
        BEGIN
            FOR constraint_name IN
                SELECT conname
                FROM pg_constraint
                WHERE conrelid = 'submissions'::regclass
                  AND contype = 'c'
                  AND pg_get_constraintdef(oid) ILIKE '%submission_type%'
            LOOP
                EXECUTE format(
                    'ALTER TABLE submissions DROP CONSTRAINT %I',
                    constraint_name
                );
            END LOOP;
        END $$;
        """
    )
    op.create_check_constraint(
        "submission_type",
        "submissions",
        "submission_type IN ('github_profile', 'profile_readme', 'repo_fork', "
        "'ctf_token', 'networking_token', 'journal_api_response', "
        "'code_analysis', 'pr_review', 'deployed_api', 'devops_analysis', "
        "'security_scanning')",
    )
