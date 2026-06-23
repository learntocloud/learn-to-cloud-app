"""validate text-value-kind retirement constraints

Validates the typed-value shape and format CHECK constraints that 0043 added
``NOT VALID``. Runs in its own transaction so the validation scan does not hold
locks during the constraint swap (matches the 0036 / 0037 and 0041 / 0042
pattern).

Revision ID: 0044_validate_retire_text_value_kind
Revises: 0043_retire_text_value_kind
Create Date: 2026-06-22
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0044_validate_retire_text_value_kind"
down_revision: str | None = "0043_retire_text_value_kind"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CONSTRAINTS = {
    "submissions": (
        "ck_submissions_typed_value_shape",
        "ck_submissions_typed_value_format",
    ),
    "verification_jobs": (
        "ck_verification_jobs_typed_value_shape",
        "ck_verification_jobs_typed_value_format",
    ),
}


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '2min'")

    for table, constraints in _CONSTRAINTS.items():
        for constraint in constraints:
            op.execute(f"ALTER TABLE {table} VALIDATE CONSTRAINT {constraint}")


def downgrade() -> None:
    pass
