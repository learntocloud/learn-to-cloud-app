"""update journal requirement ids

Revision ID: c2a7a1c6e9b2
Revises: f850574aa017
Create Date: 2026-02-03

"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "c2a7a1c6e9b2"
down_revision = "f850574aa017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Update legacy journal requirement IDs after phase reorder."""
    op.execute(
        sa.text(
            """
            UPDATE submissions
            SET requirement_id = :new_id,
                phase_id = :phase_id
            WHERE requirement_id = :old_id
            """
        ).bindparams(
            old_id="phase2-journal-fork",
            new_id="journal-starter-fork",
            phase_id=3,
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE submissions
            SET requirement_id = :new_id,
                phase_id = :phase_id
            WHERE requirement_id = :old_id
            """
        ).bindparams(
            old_id="phase2-journal-starter-fork",
            new_id="journal-starter-fork",
            phase_id=3,
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE submissions
            SET requirement_id = :new_id,
                phase_id = :phase_id
            WHERE requirement_id = :old_id
            """
        ).bindparams(
            old_id="phase2-journal-api-working",
            new_id="journal-api-response",
            phase_id=3,
        )
    )


def downgrade() -> None:
    """No-op: legacy requirement IDs are not restored."""
    return
