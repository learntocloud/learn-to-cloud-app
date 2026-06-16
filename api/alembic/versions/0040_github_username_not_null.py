"""make users.github_username non-null, drop unique constraint

Identity is the immutable GitHub numeric ID (users.id), so github_username is
display-only. Dropping the unique constraint removes the data-loss "steal the
username from the previous owner" behaviour, and NOT NULL enforces that every
authenticated user always carries their current GitHub handle.

Order matters: drop the unique constraint first, backfill any NULL usernames
with a deterministic placeholder, make the column NOT NULL via the safe
CHECK-then-flip pattern, then add a plain (non-unique) index concurrently.

Revision ID: 0040_github_username_not_null
Revises: 0039_reapply_fn_requirement_kind_lookup_grant
Create Date: 2026-05-27
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0040_github_username_not_null"
down_revision: str | None = "0039_reapply_fn_requirement_kind_lookup_grant"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '30s'")

    op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS uq_users_github_username")

    # Backfill any rows whose username was previously cleared by the old
    # username-stealing behaviour. The placeholder self-heals on next login.
    op.execute(
        "UPDATE users SET github_username = 'gh-' || id WHERE github_username IS NULL"
    )

    # NOT NULL via the CHECK-then-flip pattern (see api/.squawk.toml and 0028).
    # A plain SET NOT NULL scans the whole table under an ACCESS EXCLUSIVE lock.
    # Adding a CHECK ... NOT VALID then VALIDATE-ing it in a separate
    # transaction does the scan under a weaker lock that still allows reads and
    # writes; the later SET NOT NULL then skips the scan because the validated
    # CHECK already proves no NULLs exist. Each step is guarded so a retry works.
    op.execute(
        """
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conname = 'ck_users_github_username_nn'
          ) THEN
            ALTER TABLE users
              ADD CONSTRAINT ck_users_github_username_nn
              CHECK (github_username IS NOT NULL) NOT VALID;
          END IF;
        END$$;
        """
    )
    with op.get_context().autocommit_block():
        op.execute(
            """
            DO $$
            BEGIN
              IF EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'ck_users_github_username_nn'
                  AND NOT convalidated
              ) THEN
                ALTER TABLE users
                  VALIDATE CONSTRAINT ck_users_github_username_nn;
              END IF;
            END$$;
            """
        )
    op.execute("ALTER TABLE users ALTER COLUMN github_username SET NOT NULL")
    op.execute(
        "ALTER TABLE users DROP CONSTRAINT IF EXISTS ck_users_github_username_nn"
    )

    # CREATE INDEX CONCURRENTLY must run outside a transaction. autocommit_block
    # commits the current tx, builds the index without blocking writes, then
    # opens a fresh tx. IF NOT EXISTS keeps the statement safe to retry.
    with op.get_context().autocommit_block():
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS "
            "ix_users_github_username ON users (github_username)"
        )


def downgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '30s'")

    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_users_github_username")

    op.execute("ALTER TABLE users ALTER COLUMN github_username DROP NOT NULL")
    op.execute(
        "ALTER TABLE users "
        "ADD CONSTRAINT uq_users_github_username UNIQUE (github_username)"
    )
