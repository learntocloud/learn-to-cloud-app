"""backfill nulls and enforce NOT NULL on audit + flag columns

Revision ID: 0019_enforce_not_null_columns
Revises: 0018_drop_analytics_snapshot
Create Date: 2026-05-08

Models declare these columns as non-Optional ``Mapped[...]`` (which implies
``NOT NULL``), but the database still allows ``NULL``. Backfill any existing
``NULL`` rows with safe defaults, then enforce the constraint so the schema
matches the model declarations.
"""

import sqlalchemy as sa

from alembic import op

revision = "0019_enforce_not_null_columns"
down_revision = "0018_drop_analytics_snapshot"
branch_labels = None
depends_on = None


_NULLABLE_TIMESTAMPS = (
    ("users", "created_at"),
    ("users", "updated_at"),
    ("submissions", "created_at"),
    ("submissions", "updated_at"),
    ("verification_jobs", "created_at"),
    ("verification_jobs", "updated_at"),
    ("step_progress", "completed_at"),
)

_NULLABLE_BOOLEANS = (
    ("users", "is_admin"),
    ("submissions", "is_validated"),
    ("submissions", "verification_completed"),
)


def upgrade() -> None:
    for table, column in _NULLABLE_TIMESTAMPS:
        op.execute(
            f"UPDATE {table} SET {column} = NOW() WHERE {column} IS NULL"  # noqa: S608
        )
        op.alter_column(
            table,
            column,
            existing_type=sa.DateTime(timezone=True),
            nullable=False,
        )

    for table, column in _NULLABLE_BOOLEANS:
        op.execute(
            f"UPDATE {table} SET {column} = false WHERE {column} IS NULL"  # noqa: S608
        )
        op.alter_column(
            table,
            column,
            existing_type=sa.Boolean(),
            nullable=False,
        )


def downgrade() -> None:
    for table, column in _NULLABLE_BOOLEANS:
        op.alter_column(
            table,
            column,
            existing_type=sa.Boolean(),
            nullable=True,
        )
    for table, column in _NULLABLE_TIMESTAMPS:
        op.alter_column(
            table,
            column,
            existing_type=sa.DateTime(timezone=True),
            nullable=True,
        )
