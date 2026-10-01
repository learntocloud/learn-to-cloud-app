"""Add revocable sessions and optional explicit API runtime DML grants.

The migration owner's default ACLs apply normally. POSTGRES_API_RUNTIME_ROLE
can explicitly grant API DML when the deployment does not use default ACLs.
Downgrade discards all sessions without changing users or learning records.
"""

import os
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0060_add_auth_sessions"
down_revision: str | None = "0059_drop_user_legacy_names"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create and stamp storage atomically before the separate index builds."""
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '2min'")
    op.create_table(
        "auth_sessions",
        sa.Column("token_digest", sa.LargeBinary(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "octet_length(token_digest) = 32", name="ck_auth_sessions_digest_length"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("token_digest"),
    )
    role = os.environ.get("POSTGRES_API_RUNTIME_ROLE")
    if role:
        if not role.replace("_", "").isalnum() or len(role) > 63:
            raise ValueError("POSTGRES_API_RUNTIME_ROLE must be a valid identifier.")
        op.execute(f'GRANT SELECT, INSERT, UPDATE, DELETE ON auth_sessions TO "{role}"')


def downgrade() -> None:
    """Discard sessions only after all session-aware application processes stop."""
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '2min'")
    op.drop_table("auth_sessions")
