"""Add optional display-name storage and backfill legacy name components once.

Legacy readers and writers remain supported until the application cutover.
Downgrade discards display names; it is unsafe while display-name readers run.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0058_add_user_display_name"
down_revision: str | None = "0057_drop_verification_attempt_traceparent"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Unicode whitespace plus the four ASCII separators treated as whitespace by
# Python. Explicit code points avoid locale-dependent PostgreSQL regex classes.
_WHITESPACE = (
    r"U&'\0009\000A\000B\000C\000D\001C\001D\001E\001F\0020\0085\00A0"
    r"\1680\2000\2001\2002\2003\2004\2005\2006\2007\2008\2009\200A"
    r"\2028\2029\202F\205F\3000'"
)


def upgrade() -> None:
    """Expand atomically, preserving each nonblank legacy component exactly."""
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '2min'")
    op.add_column("users", sa.Column("display_name", sa.Text(), nullable=True))
    op.execute(
        f"""
        UPDATE users
        SET display_name = NULLIF(
            concat_ws(' ',
                CASE WHEN btrim(first_name, {_WHITESPACE}) <> ''
                     THEN first_name END,
                CASE WHEN btrim(last_name, {_WHITESPACE}) <> ''
                     THEN last_name END
            ),
            ''
        )
        """
    )


def downgrade() -> None:
    """Discard display-name storage without modifying the legacy columns."""
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '2min'")
    op.drop_column("users", "display_name")
