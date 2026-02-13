"""Add iac_token submission type.

Revision ID: 0011_add_iac_token_submission_type
Revises: 0010_step_progress_step_id_identity
Create Date: 2026-02-13
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "0011_add_iac_token_submission_type"
down_revision = "0010_step_progress_step_id_identity"
branch_labels = None
depends_on = None


def upgrade() -> None:
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
        "'ctf_token', 'networking_token', 'iac_token', 'journal_api_response', "
        "'code_analysis', 'deployed_api', 'devops_analysis', 'security_scanning')",
    )


def downgrade() -> None:
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
        "'ctf_token', 'networking_token', 'journal_api_response', 'code_analysis', "
        "'deployed_api', 'devops_analysis', 'security_scanning')",
    )
