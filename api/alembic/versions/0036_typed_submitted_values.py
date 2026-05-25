"""type submitted verification values

Revision ID: 0036_typed_submitted_values
Revises: 0035_validate_issue_448_constraints
Create Date: 2026-05-25
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0036_typed_submitted_values"
down_revision: str | None = "0035_validate_issue_448_constraints"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_VALUE_KIND_CASE = """
CASE
    WHEN requirements.submission_type IN (
        'github_profile',
        'profile_readme',
        'repo_fork',
        'pr_review',
        'journal_api_verifier',
        'devops_analysis',
        'security_scanning',
        'ci_status'
    ) THEN 'github_url'
    WHEN requirements.submission_type IN (
        'ctf_token',
        'networking_token',
        'iac_token'
    ) THEN 'token'
    WHEN requirements.submission_type = 'deployed_api' THEN 'deployed_url'
    WHEN requirements.submission_type IN (
        'journal_api_response',
        'code_analysis'
    ) THEN 'text'
END
"""

_REQUIREMENT_KIND_CHECK = """
(
    submission_type IN (
        'github_profile',
        'profile_readme',
        'repo_fork',
        'pr_review',
        'journal_api_verifier',
        'devops_analysis',
        'security_scanning',
        'ci_status'
    )
    AND submission_value_kind = 'github_url'
)
OR (
    submission_type IN (
        'ctf_token',
        'networking_token',
        'iac_token'
    )
    AND submission_value_kind = 'token'
)
OR (
    submission_type = 'deployed_api'
    AND submission_value_kind = 'deployed_url'
)
OR (
    submission_type IN (
        'journal_api_response',
        'code_analysis'
    )
    AND submission_value_kind = 'text'
)
"""

_TYPED_VALUE_SHAPE_CHECK = """
(
    submission_value_kind = 'github_url'
    AND github_url IS NOT NULL
    AND token_value IS NULL
    AND deployed_url IS NULL
    AND text_value IS NULL
    AND submitted_value = github_url
)
OR (
    submission_value_kind = 'token'
    AND token_value IS NOT NULL
    AND github_url IS NULL
    AND deployed_url IS NULL
    AND text_value IS NULL
    AND submitted_value = token_value
)
OR (
    submission_value_kind = 'deployed_url'
    AND deployed_url IS NOT NULL
    AND github_url IS NULL
    AND token_value IS NULL
    AND text_value IS NULL
    AND submitted_value = deployed_url
)
OR (
    submission_value_kind = 'text'
    AND text_value IS NOT NULL
    AND github_url IS NULL
    AND token_value IS NULL
    AND deployed_url IS NULL
    AND submitted_value = text_value
)
"""

_TYPED_VALUE_FORMAT_CHECK = """
(
    github_url IS NULL
    OR github_url ~* '^https://github[.]com/[^[:space:]]+$'
)
AND (
    deployed_url IS NULL
    OR deployed_url ~* '^https?://[^[:space:]]+$'
)
AND (
    token_value IS NULL
    OR length(btrim(token_value)) > 0
)
AND (
    text_value IS NULL
    OR length(btrim(text_value)) > 0
)
"""

_CREATE_TRIGGER_FUNCTION = """
CREATE OR REPLACE FUNCTION set_typed_submitted_value()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    expected_kind text;
BEGIN
    SELECT submission_value_kind
    INTO expected_kind
    FROM requirements
    WHERE uuid = NEW.requirement_uuid;

    IF expected_kind IS NULL THEN
        RETURN NEW;
    END IF;

    NEW.submission_value_kind = COALESCE(
        NEW.submission_value_kind,
        expected_kind
    );

    IF NEW.submission_value_kind = 'github_url'
        AND NEW.github_url IS NULL
        AND NEW.submitted_value IS NOT NULL THEN
        NEW.github_url = NEW.submitted_value;
    ELSIF NEW.submission_value_kind = 'token'
        AND NEW.token_value IS NULL
        AND NEW.submitted_value IS NOT NULL THEN
        NEW.token_value = NEW.submitted_value;
    ELSIF NEW.submission_value_kind = 'deployed_url'
        AND NEW.deployed_url IS NULL
        AND NEW.submitted_value IS NOT NULL THEN
        NEW.deployed_url = NEW.submitted_value;
    ELSIF NEW.submission_value_kind = 'text'
        AND NEW.text_value IS NULL
        AND NEW.submitted_value IS NOT NULL THEN
        NEW.text_value = NEW.submitted_value;
    END IF;

    RETURN NEW;
END
$$
"""


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '2min'")

    op.add_column(
        "requirements",
        sa.Column("submission_value_kind", sa.Text(), nullable=True),
    )
    op.add_column(
        "submissions",
        sa.Column("submission_value_kind", sa.Text(), nullable=True),
    )
    op.add_column("submissions", sa.Column("github_url", sa.Text(), nullable=True))
    op.add_column("submissions", sa.Column("token_value", sa.Text(), nullable=True))
    op.add_column("submissions", sa.Column("deployed_url", sa.Text(), nullable=True))
    op.add_column("submissions", sa.Column("text_value", sa.Text(), nullable=True))
    op.add_column(
        "verification_jobs",
        sa.Column("submission_value_kind", sa.Text(), nullable=True),
    )
    op.add_column(
        "verification_jobs",
        sa.Column("github_url", sa.Text(), nullable=True),
    )
    op.add_column(
        "verification_jobs",
        sa.Column("token_value", sa.Text(), nullable=True),
    )
    op.add_column(
        "verification_jobs",
        sa.Column("deployed_url", sa.Text(), nullable=True),
    )
    op.add_column(
        "verification_jobs",
        sa.Column("text_value", sa.Text(), nullable=True),
    )

    op.execute(
        f"""
        UPDATE requirements
        SET submission_value_kind = {_VALUE_KIND_CASE}
        """
    )
    op.execute(
        """
        DO $$
        DECLARE
            bad_count bigint;
        BEGIN
            SELECT count(*)
            INTO bad_count
            FROM requirements
            WHERE submission_value_kind IS NULL;

            IF bad_count > 0 THEN
                RAISE EXCEPTION
                    'requirements have unsupported submission_type values';
            END IF;
        END $$;
        """
    )

    _backfill_typed_values("submissions")
    _backfill_typed_values("verification_jobs")

    op.alter_column("requirements", "submission_value_kind", nullable=False)
    op.alter_column("submissions", "submission_value_kind", nullable=False)
    op.alter_column("verification_jobs", "submission_value_kind", nullable=False)

    with op.get_context().autocommit_block():
        op.execute(
            """
            CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS
            uq_requirements_uuid_value_kind
            ON requirements (uuid, submission_value_kind)
            """
        )
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'uq_requirements_uuid_value_kind'
            ) THEN
                ALTER TABLE requirements
                ADD CONSTRAINT uq_requirements_uuid_value_kind
                UNIQUE USING INDEX uq_requirements_uuid_value_kind;
            END IF;
        END $$
        """
    )
    _add_check_constraint_not_valid(
        "ck_requirements_submission_value_kind_matches_type",
        "requirements",
        _REQUIREMENT_KIND_CHECK,
    )
    _add_typed_value_constraints("submissions", "ck_submissions")
    _add_typed_value_constraints("verification_jobs", "ck_verification_jobs")
    _add_value_kind_fk("submissions", "fk_submissions_requirement_value_kind")
    _add_value_kind_fk(
        "verification_jobs",
        "fk_verification_jobs_requirement_value_kind",
    )

    op.execute(_CREATE_TRIGGER_FUNCTION)
    _create_trigger("submissions", "trg_submissions_set_typed_submitted_value")
    _create_trigger(
        "verification_jobs",
        "trg_verification_jobs_set_typed_submitted_value",
    )


def downgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '2min'")

    op.execute(
        "DROP TRIGGER IF EXISTS trg_verification_jobs_set_typed_submitted_value "
        "ON verification_jobs"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS trg_submissions_set_typed_submitted_value "
        "ON submissions"
    )
    op.execute("DROP FUNCTION IF EXISTS set_typed_submitted_value()")

    op.drop_constraint(
        "fk_verification_jobs_requirement_value_kind",
        "verification_jobs",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_submissions_requirement_value_kind",
        "submissions",
        type_="foreignkey",
    )
    _drop_typed_value_constraints("verification_jobs", "ck_verification_jobs")
    _drop_typed_value_constraints("submissions", "ck_submissions")
    op.drop_constraint(
        "ck_requirements_submission_value_kind_matches_type",
        "requirements",
        type_="check",
    )
    op.drop_constraint(
        "uq_requirements_uuid_value_kind",
        "requirements",
        type_="unique",
    )

    for table in ("verification_jobs", "submissions"):
        for column in (
            "text_value",
            "deployed_url",
            "token_value",
            "github_url",
            "submission_value_kind",
        ):
            op.drop_column(table, column)
    op.drop_column("requirements", "submission_value_kind")


def _backfill_typed_values(table: str) -> None:
    op.execute(
        f"""
        UPDATE {table}
        SET
            submission_value_kind = requirements.submission_value_kind,
            github_url = CASE
                WHEN requirements.submission_value_kind = 'github_url'
                THEN btrim({table}.submitted_value)
            END,
            token_value = CASE
                WHEN requirements.submission_value_kind = 'token'
                THEN btrim({table}.submitted_value)
            END,
            deployed_url = CASE
                WHEN requirements.submission_value_kind = 'deployed_url'
                THEN btrim({table}.submitted_value)
            END,
            text_value = CASE
                WHEN requirements.submission_value_kind = 'text'
                THEN btrim({table}.submitted_value)
            END,
            submitted_value = btrim({table}.submitted_value)
        FROM requirements
        WHERE {table}.requirement_uuid = requirements.uuid
        """
    )


def _add_typed_value_constraints(table: str, prefix: str) -> None:
    _add_check_constraint_not_valid(
        f"{prefix}_typed_value_shape",
        table,
        _TYPED_VALUE_SHAPE_CHECK,
    )
    _add_check_constraint_not_valid(
        f"{prefix}_typed_value_format",
        table,
        _TYPED_VALUE_FORMAT_CHECK,
    )


def _drop_typed_value_constraints(table: str, prefix: str) -> None:
    op.drop_constraint(f"{prefix}_typed_value_format", table, type_="check")
    op.drop_constraint(f"{prefix}_typed_value_shape", table, type_="check")


def _add_value_kind_fk(table: str, name: str) -> None:
    op.execute(
        f"""
        ALTER TABLE {table}
        ADD CONSTRAINT {name}
        FOREIGN KEY (requirement_uuid, submission_value_kind)
        REFERENCES requirements (uuid, submission_value_kind)
        ON DELETE RESTRICT
        NOT VALID
        """
    )


def _add_check_constraint_not_valid(name: str, table: str, condition: str) -> None:
    op.execute(
        f"""
        ALTER TABLE {table}
        ADD CONSTRAINT {name}
        CHECK ({condition})
        NOT VALID
        """
    )


def _create_trigger(table: str, name: str) -> None:
    op.execute(
        f"""
        CREATE TRIGGER {name}
        BEFORE INSERT OR UPDATE OF
            requirement_uuid,
            submitted_value,
            submission_value_kind,
            github_url,
            token_value,
            deployed_url,
            text_value
        ON {table}
        FOR EACH ROW
        EXECUTE FUNCTION set_typed_submitted_value()
        """
    )
