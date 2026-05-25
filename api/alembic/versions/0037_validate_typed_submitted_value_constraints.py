"""validate typed submitted value constraints

Revision ID: 0037_validate_typed_submitted_value_constraints
Revises: 0036_typed_submitted_values
Create Date: 2026-05-25
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0037_validate_typed_submitted_value_constraints"
down_revision: str | None = "0036_typed_submitted_values"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '2min'")

    for table, constraints in {
        "requirements": ("ck_requirements_submission_value_kind_matches_type",),
        "submissions": (
            "ck_submissions_typed_value_shape",
            "ck_submissions_typed_value_format",
            "fk_submissions_requirement_value_kind",
        ),
        "verification_jobs": (
            "ck_verification_jobs_typed_value_shape",
            "ck_verification_jobs_typed_value_format",
            "fk_verification_jobs_requirement_value_kind",
        ),
    }.items():
        for constraint in constraints:
            op.execute(f"ALTER TABLE {table} VALIDATE CONSTRAINT {constraint}")


def downgrade() -> None:
    pass
