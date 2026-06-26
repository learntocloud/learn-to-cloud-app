"""validate reintroduced text-value-kind constraints

Validates the typed-value shape and format CHECK constraints on ``submissions``
and ``verification_jobs``, plus the ``requirements`` type-to-kind CHECK, that
0045 added ``NOT VALID``. Runs in its own transaction so the validation scan
does not hold locks during the constraint swap (matches the 0043 / 0044 and
0041 / 0042 pattern).

Revision ID: 0046_validate_reintroduce_text_value_kind
Revises: 0045_reintroduce_text_value_kind
Create Date: 2026-06-26
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0046_validate_reintroduce_text_value_kind"
down_revision: str | None = "0045_reintroduce_text_value_kind"
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
    "requirements": ("ck_requirements_submission_value_kind_matches_type",),
}


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '2min'")

    for table, constraints in _CONSTRAINTS.items():
        for constraint in constraints:
            op.execute(f"ALTER TABLE {table} VALIDATE CONSTRAINT {constraint}")


def downgrade() -> None:
    pass
