"""clear submissions for stable requirement ids

Revision ID: d3b1b2f4c9a0
Revises: c2a7a1c6e9b2
Create Date: 2026-02-03

"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "d3b1b2f4c9a0"
down_revision = "c2a7a1c6e9b2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Clear submissions to avoid mismatched legacy requirement IDs."""
    op.execute(sa.text("DELETE FROM submissions"))


def downgrade() -> None:
    """No-op: deleted submissions cannot be restored."""
    return
