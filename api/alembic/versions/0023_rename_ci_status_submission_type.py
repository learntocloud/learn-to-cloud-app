"""Rename ci_status submission type to journal_api_verifier.

Reflects the real Phase 3 verification contract: CI gate plus LLM rubric
review.  Migrates existing rows and updates check constraints on both
submissions and verification_jobs.

Revision ID: 0023_rename_ci_status_submission_type
Revises: 0022_drop_verification_job_legacy_columns
Create Date: 2026-05-21
"""

from __future__ import annotations

from alembic import op

revision = "0023_rename_ci_status_submission_type"
down_revision = "0022_drop_verification_job_legacy_columns"
branch_labels = None
depends_on = None

_DROP_CONSTRAINT_SQL = """
DO $$
DECLARE
    constraint_name text;
BEGIN
    FOR constraint_name IN
        SELECT conname
        FROM pg_constraint
        WHERE conrelid = '{table}'::regclass
          AND contype = 'c'
          AND pg_get_constraintdef(oid) ILIKE '%submission_type%'
    LOOP
        EXECUTE format(
            'ALTER TABLE {table} DROP CONSTRAINT %I',
            constraint_name
        );
    END LOOP;
END $$;
"""

_SUBMISSIONS_CONSTRAINT = (
    "submission_type IN ('github_profile', 'profile_readme', 'repo_fork', "
    "'ctf_token', 'networking_token', 'journal_api_response', "
    "'pr_review', 'journal_api_verifier', 'deployed_api', "
    "'devops_analysis', 'security_scanning')"
)

_VERIFICATION_JOBS_CONSTRAINT = (
    "submission_type IN ('github_profile', 'profile_readme', 'repo_fork', "
    "'ctf_token', 'networking_token', 'journal_api_response', "
    "'code_analysis', 'pr_review', 'journal_api_verifier', 'deployed_api', "
    "'devops_analysis', 'security_scanning')"
)


def upgrade() -> None:
    # Drop constraints first so the UPDATE below isn't blocked by the old
    # constraint that doesn't include journal_api_verifier
    op.execute(_DROP_CONSTRAINT_SQL.format(table="submissions"))
    op.execute(_DROP_CONSTRAINT_SQL.format(table="verification_jobs"))

    # Migrate existing ci_status rows on both tables
    op.execute(
        "UPDATE submissions SET submission_type = 'journal_api_verifier' "
        "WHERE submission_type = 'ci_status'"
    )
    op.execute(
        "UPDATE verification_jobs SET submission_type = 'journal_api_verifier' "
        "WHERE submission_type = 'ci_status'"
    )

    # Add new check constraints with journal_api_verifier instead of ci_status
    op.create_check_constraint(
        "submission_type",
        "submissions",
        _SUBMISSIONS_CONSTRAINT,
    )
    op.create_check_constraint(
        "submission_type",
        "verification_jobs",
        _VERIFICATION_JOBS_CONSTRAINT,
    )


def downgrade() -> None:
    # Restore ci_status rows
    op.execute(
        "UPDATE submissions SET submission_type = 'ci_status' "
        "WHERE submission_type = 'journal_api_verifier'"
    )
    op.execute(
        "UPDATE verification_jobs SET submission_type = 'ci_status' "
        "WHERE submission_type = 'journal_api_verifier'"
    )

    op.execute(_DROP_CONSTRAINT_SQL.format(table="submissions"))
    op.create_check_constraint(
        "submission_type",
        "submissions",
        (
            "submission_type IN ('github_profile', 'profile_readme', 'repo_fork', "
            "'ctf_token', 'networking_token', 'journal_api_response', "
            "'pr_review', 'ci_status', 'deployed_api', "
            "'devops_analysis', 'security_scanning')"
        ),
    )

    op.execute(_DROP_CONSTRAINT_SQL.format(table="verification_jobs"))
    op.create_check_constraint(
        "submission_type",
        "verification_jobs",
        (
            "submission_type IN ('github_profile', 'profile_readme', 'repo_fork', "
            "'ctf_token', 'networking_token', 'journal_api_response', "
            "'code_analysis', 'pr_review', 'ci_status', 'deployed_api', "
            "'devops_analysis', 'security_scanning')"
        ),
    )
