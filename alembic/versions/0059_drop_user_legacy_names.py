"""Remove obsolete name components after the display-name application cutover.

Downgrade restores empty legacy columns, not their discarded values.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0059_drop_user_legacy_names"
down_revision: str | None = "0058_add_user_display_name"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Drop legacy storage without changing canonical display names."""
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '2min'")
    op.drop_column("users", "first_name")
    op.drop_column("users", "last_name")


def downgrade() -> None:
    """Restore nullable legacy columns without inferring name components."""
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '2min'")
    op.add_column("users", sa.Column("first_name", sa.String(255), nullable=True))
    op.add_column("users", sa.Column("last_name", sa.String(255), nullable=True))
