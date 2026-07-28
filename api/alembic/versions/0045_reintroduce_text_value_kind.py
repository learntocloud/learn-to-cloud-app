"""reintroduce the text value kind for career reflection

Phase 7 (Interview & Job Prep) adds a ``career_reflection`` submission type whose
answers are stored as free text. The ``text`` submitted-value kind was retired in
0043 once nothing used it; this migration brings it back, scoped to the new
``career_reflection`` type.

This migration:

- Adds the ``text_value`` column back to ``submissions`` and
  ``verification_jobs``.
- Replaces the typed-value shape and format CHECK constraints on both tables
  with versions that include the ``text`` branch / ``text_value`` column.
- Recreates the ``set_typed_submitted_value`` trigger function and its two
  triggers with the ``text`` branch so ``text_value`` is populated from
  ``submitted_value``.
- Extends ``ck_requirements_submission_value_kind_matches_type`` so the
  ``career_reflection`` submission type maps to the ``text`` value kind.

All swapped CHECK constraints are added ``NOT VALID`` here and validated in the
follow-up migration 0046 (matches the 0043 / 0044 pattern, keeping the
validation scan out of this transaction).

Revision ID: 0045_reintroduce_text_value_kind
Revises: 0044_validate_retire_text_value_kind
Create Date: 2026-06-26
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0045_reintroduce_text_value_kind"
down_revision: str | None = "0044_validate_retire_text_value_kind"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Trigger function with the ``text`` branch (mirrors the pre-0043 shape).
_TRIGGER_FUNCTION_WITH_TEXT = """
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

# Trigger function without the ``text`` branch, restored on downgrade.
_TRIGGER_FUNCTION_NO_TEXT = """
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
    END IF;

    RETURN NEW;
END
$$
"""

# Shape check with the ``text`` branch / ``text_value`` column.
_SHAPE_CHECK_WITH_TEXT = """
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

# Shape check without the ``text`` branch, restored on downgrade.
_SHAPE_CHECK_NO_TEXT = """
(
    submission_value_kind = 'github_url'
    AND github_url IS NOT NULL
    AND token_value IS NULL
    AND deployed_url IS NULL
    AND submitted_value = github_url
)
OR (
    submission_value_kind = 'token'
    AND token_value IS NOT NULL
    AND github_url IS NULL
    AND deployed_url IS NULL
    AND submitted_value = token_value
)
OR (
    submission_value_kind = 'deployed_url'
    AND deployed_url IS NOT NULL
    AND github_url IS NULL
    AND token_value IS NULL
    AND submitted_value = deployed_url
)
"""

# Format check with the ``text_value`` clause.
_FORMAT_CHECK_WITH_TEXT = """
(
    github_url IS NULL
    OR length(btrim(github_url)) > 0
)
AND (
    deployed_url IS NULL
    OR length(btrim(deployed_url)) > 0
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

# Format check without the ``text_value`` clause, restored on downgrade.
_FORMAT_CHECK_NO_TEXT = """
(
    github_url IS NULL
    OR length(btrim(github_url)) > 0
)
AND (
    deployed_url IS NULL
    OR length(btrim(deployed_url)) > 0
)
AND (
    token_value IS NULL
    OR length(btrim(token_value)) > 0
)
"""

# Requirements type-to-kind check with the ``career_reflection`` -> ``text`` row.
_REQUIREMENTS_CHECK_WITH_TEXT = """
(
    submission_type IN (
        'github_profile',
        'profile_readme',
        'repo_fork',
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
    submission_type = 'career_reflection'
    AND submission_value_kind = 'text'
)
"""

# Requirements check without the ``career_reflection`` row, restored on downgrade.
_REQUIREMENTS_CHECK_NO_TEXT = """
(
    submission_type IN (
        'github_profile',
        'profile_readme',
        'repo_fork',
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
"""

_REQUIREMENTS_CONSTRAINT = "ck_requirements_submission_value_kind_matches_type"

_TABLES = (
    ("submissions", "ck_submissions"),
    ("verification_jobs", "ck_verification_jobs"),
)


def _replace_check_not_valid(table: str, name: str, condition: str) -> None:
    op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {name}")
    op.execute(
        f"""
        ALTER TABLE {table}
        ADD CONSTRAINT {name}
        CHECK ({condition})
        NOT VALID
        """
    )


def _recreate_trigger(table: str, *, include_text_value: bool) -> None:
    name = f"trg_{table}_set_typed_submitted_value"
    text_column = ",\n            text_value" if include_text_value else ""
    op.execute(f"DROP TRIGGER IF EXISTS {name} ON {table}")
    op.execute(
        f"""
        CREATE TRIGGER {name}
        BEFORE INSERT OR UPDATE OF
            requirement_uuid,
            submitted_value,
            submission_value_kind,
            github_url,
            token_value,
            deployed_url{text_column}
        ON {table}
        FOR EACH ROW
        EXECUTE FUNCTION set_typed_submitted_value()
        """
    )


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '30s'")

    op.add_column("submissions", sa.Column("text_value", sa.Text(), nullable=True))
    op.add_column(
        "verification_jobs",
        sa.Column("text_value", sa.Text(), nullable=True),
    )

    for table, prefix in _TABLES:
        _replace_check_not_valid(
            table,
            f"{prefix}_typed_value_shape",
            _SHAPE_CHECK_WITH_TEXT,
        )
        _replace_check_not_valid(
            table,
            f"{prefix}_typed_value_format",
            _FORMAT_CHECK_WITH_TEXT,
        )

    op.execute(_TRIGGER_FUNCTION_WITH_TEXT)
    for table, _prefix in _TABLES:
        _recreate_trigger(table, include_text_value=True)

    op.execute(
        f"ALTER TABLE requirements DROP CONSTRAINT IF EXISTS {_REQUIREMENTS_CONSTRAINT}"
    )
    op.execute(
        f"""
        ALTER TABLE requirements
        ADD CONSTRAINT {_REQUIREMENTS_CONSTRAINT}
        CHECK ({_REQUIREMENTS_CHECK_WITH_TEXT})
        NOT VALID
        """
    )


def downgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '30s'")

    op.execute(
        f"ALTER TABLE requirements DROP CONSTRAINT IF EXISTS {_REQUIREMENTS_CONSTRAINT}"
    )
    op.execute(
        f"""
        ALTER TABLE requirements
        ADD CONSTRAINT {_REQUIREMENTS_CONSTRAINT}
        CHECK ({_REQUIREMENTS_CHECK_NO_TEXT})
        NOT VALID
        """
    )

    op.execute(_TRIGGER_FUNCTION_NO_TEXT)
    for table, _prefix in _TABLES:
        _recreate_trigger(table, include_text_value=False)

    for table, prefix in _TABLES:
        _replace_check_not_valid(
            table,
            f"{prefix}_typed_value_shape",
            _SHAPE_CHECK_NO_TEXT,
        )
        _replace_check_not_valid(
            table,
            f"{prefix}_typed_value_format",
            _FORMAT_CHECK_NO_TEXT,
        )

    op.drop_column("submissions", "text_value")
    op.drop_column("verification_jobs", "text_value")
