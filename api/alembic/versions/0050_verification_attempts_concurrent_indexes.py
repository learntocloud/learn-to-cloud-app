"""create verification_attempts indexes concurrently

Why this change: split out from revision 0049 so the table creation,
backfill, trigger, and grants stamp atomically inside one transaction,
while the three supporting indexes on ``verification_attempts`` build
CONCURRENTLY here. Isolating the concurrent builds means a failed or
retried index revision can never leave 0049 half-applied.

Retry safety: a failed ``CREATE INDEX CONCURRENTLY`` leaves an *invalid*
index behind, and a bare ``IF NOT EXISTS`` retry would see the name and
skip the rebuild, letting Alembic stamp this revision with a broken
index. So each index is ``DROP INDEX CONCURRENTLY IF EXISTS``-ed first --
removing any invalid/partial leftover -- before being (re)created. The
``IF NOT EXISTS`` on the create is retained only to satisfy the repo's
migration lint; because the drop always runs first, it never causes an
invalid index to be skipped. Every run converges on a fresh, valid index.

Timeout handling: the concurrent builds run in autocommit mode, where a
top-level ``SET LOCAL`` would not survive (autocommit_block commits the
surrounding transaction). We keep the ``SET LOCAL`` at the top only to
satisfy the repository's migration-lint timeout convention, and set
*session-level* ``lock_timeout`` / ``statement_timeout`` inside the
autocommit block to actually bound the builds, ``RESET``-ing them in a
``finally`` so nothing leaks onto the pooled connection.

Schema effect (all CONCURRENTLY, in an autocommit block):
- ``uq_verification_attempts_active_user_req`` -- partial UNIQUE on
  ``(user_id, requirement_uuid) WHERE outcome IS NULL`` (one active
  attempt per user/requirement).
- ``ix_verification_attempts_succeeded_user_req`` -- partial on
  ``(user_id, requirement_uuid) WHERE outcome = 'succeeded'``.
- ``ix_verification_attempts_user_req_created`` -- latest-history lookup
  on ``(user_id, requirement_uuid, created_at DESC)``.

Rollback notes: downgrade drops the three indexes CONCURRENTLY.

Revision ID: 0050_verification_attempts_concurrent_indexes
Revises: 0049_add_verification_attempts_and_step_completions
Create Date: 2026-07-14
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0050_verification_attempts_concurrent_indexes"
down_revision: str | None = "0049_add_verification_attempts_and_step_completions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# (index name, CREATE statement). Order is not significant; each build is
# independent and idempotent via the drop-then-create pattern below.
_INDEXES: tuple[tuple[str, str], ...] = (
    (
        "uq_verification_attempts_active_user_req",
        "CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS "
        "uq_verification_attempts_active_user_req "
        "ON verification_attempts (user_id, requirement_uuid) "
        "WHERE outcome IS NULL",
    ),
    (
        "ix_verification_attempts_succeeded_user_req",
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS "
        "ix_verification_attempts_succeeded_user_req "
        "ON verification_attempts (user_id, requirement_uuid) "
        "WHERE outcome = 'succeeded'",
    ),
    (
        "ix_verification_attempts_user_req_created",
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS "
        "ix_verification_attempts_user_req_created "
        "ON verification_attempts (user_id, requirement_uuid, created_at DESC)",
    ),
)


def upgrade() -> None:
    # SET LOCAL keeps the repo's migration-lint timeout convention happy for
    # this transaction; the effective bounds for the concurrent builds are
    # the session-level settings applied inside the autocommit block below.
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '10min'")

    with op.get_context().autocommit_block():
        op.execute("SET lock_timeout = '5s'")
        op.execute("SET statement_timeout = '10min'")
        try:
            for name, create_stmt in _INDEXES:
                # Drop any prior (possibly INVALID) build first, then create
                # fresh so a retried run cannot stamp an invalid index.
                op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {name}")
                op.execute(create_stmt)
        finally:
            op.execute("RESET statement_timeout")
            op.execute("RESET lock_timeout")


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("SET lock_timeout = '5s'")
        op.execute("SET statement_timeout = '10min'")
        try:
            for name, _ in reversed(_INDEXES):
                op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {name}")
        finally:
            op.execute("RESET statement_timeout")
            op.execute("RESET lock_timeout")
