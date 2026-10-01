"""Close legacy active attempts and index pending API verification work."""

from collections.abc import Sequence

from alembic import op

revision: str = "0062_api_verification_worker"
down_revision: str | None = "0061_auth_sessions_concurrent_indexes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Run after stopping Functions; preserve all completed learner results."""
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '30s'")
    op.execute(
        """
        UPDATE verification_attempts
        SET outcome = 'server_error',
            error_code = 'verification_interrupted',
            validation_message = 'Verification was interrupted by an update. '
                'This attempt was not counted. Please try again.',
            terminal_source = 'api_worker_cutover',
            completed_at = now(),
            updated_at = now()
        WHERE outcome IS NULL
        """
    )
    with op.get_context().autocommit_block():
        op.execute("SET lock_timeout = '5s'")
        op.execute("SET statement_timeout = '10min'")
        try:
            op.execute(
                "DROP INDEX CONCURRENTLY IF EXISTS ix_verification_attempts_pending"
            )
            op.execute(
                "CREATE INDEX CONCURRENTLY IF NOT EXISTS "
                "ix_verification_attempts_pending "
                "ON verification_attempts (created_at, id) "
                "WHERE outcome IS NULL AND started_at IS NULL"
            )
        finally:
            op.execute("RESET statement_timeout")
            op.execute("RESET lock_timeout")


def downgrade() -> None:
    """Remove the index; finalized attempts remain history and are not requeued."""
    with op.get_context().autocommit_block():
        op.execute("SET lock_timeout = '5s'")
        op.execute("SET statement_timeout = '10min'")
        try:
            op.execute(
                "DROP INDEX CONCURRENTLY IF EXISTS ix_verification_attempts_pending"
            )
        finally:
            op.execute("RESET statement_timeout")
            op.execute("RESET lock_timeout")
