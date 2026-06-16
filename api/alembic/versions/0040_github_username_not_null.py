"""make users.github_username non-null, drop unique constraint

Identity is the immutable GitHub numeric ID (users.id), so github_username is
display-only. Dropping the unique constraint removes the data-loss "steal the
username from the previous owner" behaviour, and NOT NULL enforces that every
authenticated user always carries their current GitHub handle.

Order matters: drop the unique constraint first, backfill any NULL usernames
with a deterministic placeholder, then set NOT NULL, then add a plain
(non-unique) index for lookups.

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
    op.drop_constraint("uq_users_github_username", "users", type_="unique")

    # Backfill any rows whose username was previously cleared by the old
    # username-stealing behaviour. The placeholder self-heals on next login.
    op.execute(
        "UPDATE users SET github_username = 'gh-' || id WHERE github_username IS NULL"
    )

    op.alter_column("users", "github_username", nullable=False)
    op.create_index("ix_users_github_username", "users", ["github_username"])


def downgrade() -> None:
    op.drop_index("ix_users_github_username", table_name="users")
    op.alter_column("users", "github_username", nullable=True)
    op.create_unique_constraint(
        "uq_users_github_username", "users", ["github_username"]
    )
