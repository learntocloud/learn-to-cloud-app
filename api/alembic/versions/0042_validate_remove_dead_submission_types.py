"""validate the tightened requirements submission-type constraint

Validates the ``NOT VALID`` constraint added in 0041 in its own transaction, so
the validation scan does not block reads alongside the swap (matches the
0036 / 0037 split).

Revision ID: 0042_validate_remove_dead_submission_types
Revises: 0041_remove_dead_submission_types
Create Date: 2026-06-21
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0042_validate_remove_dead_submission_types"
down_revision: str | None = "0041_remove_dead_submission_types"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CONSTRAINT = "ck_requirements_submission_value_kind_matches_type"


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '2min'")

    op.execute(f"ALTER TABLE requirements VALIDATE CONSTRAINT {_CONSTRAINT}")


def downgrade() -> None:
    pass
