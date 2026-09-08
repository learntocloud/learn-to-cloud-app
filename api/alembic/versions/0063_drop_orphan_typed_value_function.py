"""Drop the typed-value trigger function left behind by legacy table removal."""

from collections.abc import Sequence

from alembic import op

revision: str = "0063_drop_orphan_typed_value_function"
down_revision: str | None = "0062_api_verification_worker"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '30s'")
    op.execute("DROP FUNCTION IF EXISTS public.set_typed_submitted_value() RESTRICT")


def downgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '30s'")
    op.execute(
        """
CREATE FUNCTION public.set_typed_submitted_value()
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
    )
