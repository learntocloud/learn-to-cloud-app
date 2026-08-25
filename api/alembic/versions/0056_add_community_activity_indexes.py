"""add indexes for community activity aggregates

Why this change: the public community page aggregates recent verification
attempts by ``created_at`` and successful projects by ``completed_at``. These
indexes keep the rolling activity query bounded as attempt history grows.

Schema effect:
- Adds an index on ``verification_attempts.created_at``.
- Adds a partial succeeded-attempt index on ``(completed_at, requirement_uuid,
  user_id)``.

Both indexes are built concurrently so production verification writes remain
available while the migration runs. The downgrade removes them concurrently.

Revision ID: 0056_add_community_activity_indexes
Revises: 0055_drop_legacy_curriculum_contract
Create Date: 2026-08-25
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0056_add_community_activity_indexes"
down_revision: str | None = "0055_drop_legacy_curriculum_contract"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_INDEXES: tuple[tuple[str, str], ...] = (
    (
        "ix_verification_attempts_created_at",
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS "
        "ix_verification_attempts_created_at "
        "ON verification_attempts (created_at)",
    ),
    (
        "ix_verification_attempts_succeeded_completed_requirement_user",
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS "
        "ix_verification_attempts_succeeded_completed_requirement_user "
        "ON verification_attempts (completed_at, requirement_uuid, user_id) "
        "WHERE outcome = 'succeeded'",
    ),
)


def upgrade() -> None:
    """Build community activity indexes without blocking verification writes."""
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '10min'")

    with op.get_context().autocommit_block():
        op.execute("SET lock_timeout = '5s'")
        op.execute("SET statement_timeout = '10min'")
        try:
            for name, create_stmt in _INDEXES:
                op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {name}")
                op.execute(create_stmt)
        finally:
            op.execute("RESET statement_timeout")
            op.execute("RESET lock_timeout")


def downgrade() -> None:
    """Remove community activity indexes without blocking verification writes."""
    with op.get_context().autocommit_block():
        op.execute("SET lock_timeout = '5s'")
        op.execute("SET statement_timeout = '10min'")
        try:
            for name, _ in reversed(_INDEXES):
                op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {name}")
        finally:
            op.execute("RESET statement_timeout")
            op.execute("RESET lock_timeout")
