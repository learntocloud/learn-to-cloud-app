"""retire the text value kind

Removes the now-unreachable ``text`` submitted-value kind. After the dead
submission types were dropped (#560 / migration 0041), no submission type maps
to ``text``, so the ``text_value`` column and every constraint / trigger branch
that mentions it are dead weight.

This migration:

- Guards at apply time that no ``submissions`` / ``verification_jobs`` /
  ``requirements`` row uses ``submission_value_kind = 'text'`` (or a non-null
  ``text_value``) and refuses to proceed otherwise, so data is never silently
  dropped. Production was confirmed clean (zero such rows) before this migration
  was written.
- Recreates the ``set_typed_submitted_value`` trigger function and its two
  triggers without the ``text`` branch / ``text_value`` column, so the column
  can be dropped without a dangling dependency.
- Replaces the typed-value shape and format CHECK constraints on
  ``submissions`` and ``verification_jobs`` with versions that no longer mention
  the ``text`` kind or ``text_value``. They are added ``NOT VALID`` here and
  validated in the follow-up migration 0044 (matches the 0036 / 0037 pattern,
  keeps the validation scan out of this transaction, and keeps squawk happy).
- Drops the ``text_value`` column from both tables.

The matching application code that referenced ``text_value`` /
``SubmissionValueKind.TEXT`` is removed in the same change, so the destructive
column drop follows the repo's documented rolling-deploy tradeoff: briefly,
draining old pods may error once the column is gone.

Revision ID: 0043_retire_text_value_kind
Revises: 0042_validate_remove_dead_submission_types
Create Date: 2026-06-22
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0043_retire_text_value_kind"
down_revision: str | None = "0042_validate_remove_dead_submission_types"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Refuse to drop the text path if any row still uses it. Raises with a clear
# message so an operator investigates instead of losing data silently.
_GUARD = """
DO $$
DECLARE
    offending bigint;
BEGIN
    SELECT
        (SELECT count(*) FROM submissions
         WHERE submission_value_kind = 'text' OR text_value IS NOT NULL)
      + (SELECT count(*) FROM verification_jobs
         WHERE submission_value_kind = 'text' OR text_value IS NOT NULL)
      + (SELECT count(*) FROM requirements
         WHERE submission_value_kind = 'text')
    INTO offending;

    IF offending > 0 THEN
        RAISE EXCEPTION
            'Found % row(s) still using the text value kind. '
            'Resolve these rows manually before retiring the text path.',
            offending;
    END IF;
END $$;
"""

# Trigger function without the ``text`` branch. ``text_value`` is no longer
# referenced so the column can be dropped after this runs.
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

# Prior trigger function, restored on downgrade (with the ``text`` branch).
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

# Shape check without the ``text`` branch / ``text_value`` column.
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

# Prior shape check, restored on downgrade (with the ``text`` branch).
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

# Format check without the ``text_value`` clause.
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

# Prior format check, restored on downgrade (with the ``text_value`` clause).
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

    op.execute(_GUARD)

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


def downgrade() -> None:
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
