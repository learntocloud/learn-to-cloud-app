"""Build session indexes separately from the atomic storage migration.

Drop partial or invalid builds before retrying, rather than skipping their names.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0061_auth_sessions_concurrent_indexes"
down_revision: str | None = "0060_add_auth_sessions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COLUMNS = ("user_id", "expires_at", "last_seen_at")


def upgrade() -> None:
    """Rebuild each index concurrently with bounded session-level timeouts."""
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '10min'")
    with op.get_context().autocommit_block():
        op.execute("SET lock_timeout = '5s'")
        op.execute("SET statement_timeout = '10min'")
        try:
            for column in _COLUMNS:
                name = f"ix_auth_sessions_{column}"
                op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {name}")
                op.execute(
                    f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {name} "
                    f"ON auth_sessions ({column})"
                )
        finally:
            op.execute("RESET statement_timeout")
            op.execute("RESET lock_timeout")


def downgrade() -> None:
    """Drop secondary indexes before the table migration is reversed."""
    with op.get_context().autocommit_block():
        op.execute("SET lock_timeout = '5s'")
        op.execute("SET statement_timeout = '10min'")
        try:
            for column in reversed(_COLUMNS):
                op.execute(
                    f"DROP INDEX CONCURRENTLY IF EXISTS ix_auth_sessions_{column}"
                )
        finally:
            op.execute("RESET statement_timeout")
            op.execute("RESET lock_timeout")
