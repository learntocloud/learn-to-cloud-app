"""convert submissions.feedback_json from TEXT to JSONB

Issue #459: ``submissions.feedback_json`` was originally TEXT holding a
JSON-serialized list of TaskResult records. Now that #425 surfaces
rubric feedback for passing submissions too, every multi-task
verification persists a feedback payload, so the column earns a real
JSONB type: structured types in SQLAlchemy, smaller storage, no
``json.dumps``/``json.loads`` boilerplate in app code, and future
query-inside-the-JSON optionality.

Schema effect:
- ``submissions.feedback_json`` TEXT -> JSONB (using
  ``feedback_json::jsonb`` cast).

Safety:
- The cast rejects malformed rows. Preflight on prod confirmed all
  existing non-null rows parse (see PR body).
- Idempotent via ``pg_typeof`` check.
- Single ALTER TABLE under ACCESS EXCLUSIVE; the table is small
  (one row per validation attempt) so the lock window is brief.

Revision ID: 0032_feedback_json_jsonb
Revises: 0031_drop_legacy_ids
Create Date: 2026-05-24
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0032_feedback_json_jsonb"
down_revision: str | None = "0031_drop_legacy_ids"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'submissions'
                  AND column_name = 'feedback_json'
                  AND data_type = 'text'
            ) THEN
                ALTER TABLE submissions
                ALTER COLUMN feedback_json TYPE JSONB
                USING feedback_json::jsonb;
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'submissions'
                  AND column_name = 'feedback_json'
                  AND data_type = 'jsonb'
            ) THEN
                ALTER TABLE submissions
                ALTER COLUMN feedback_json TYPE TEXT
                USING feedback_json::text;
            END IF;
        END $$;
        """
    )
