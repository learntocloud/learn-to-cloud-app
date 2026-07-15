"""Seed authoritative learner progress for local UI testing.

Usage: uv run --directory api python ../scripts/seed_progress.py <github_username>
"""

import asyncio
import os
import sys
from datetime import UTC, datetime
from uuid import uuid4

from learn_to_cloud_shared.content_catalog import get_curriculum_catalog
from learn_to_cloud_shared.submission_values import value_kind_for_submission_type
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

database_url = os.environ.get(
    "DATABASE__URL", "******db:5432/learn_to_cloud"
)


async def main(github_username: str) -> None:
    catalog = get_curriculum_catalog()
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as conn:
            row = (
                await conn.execute(
                    text(
                        "SELECT id, github_username FROM users "
                        "WHERE github_username = :username"
                    ),
                    {"username": github_username},
                )
            ).first()
            if row is None:
                print(f"ERROR: User '{github_username}' not found.")
                sys.exit(1)

            user_id = row.id
            now = datetime.now(UTC)

            await conn.execute(
                text(
                    "DELETE FROM learner_step_completions WHERE user_id = :user_id"
                ),
                {"user_id": user_id},
            )
            for step_uuid in catalog.active_step_uuids:
                await conn.execute(
                    text(
                        """
                        INSERT INTO learner_step_completions
                            (user_id, step_uuid, completed_at)
                        VALUES (:user_id, :step_uuid, :completed_at)
                        """
                    ),
                    {
                        "user_id": user_id,
                        "step_uuid": step_uuid,
                        "completed_at": now,
                    },
                )

            await conn.execute(
                text("DELETE FROM verification_attempts WHERE user_id = :user_id"),
                {"user_id": user_id},
            )
            for requirement_uuid in catalog.active_requirement_uuids:
                requirement = catalog.requirements_by_uuid[requirement_uuid]
                await conn.execute(
                    text(
                        """
                        INSERT INTO verification_attempts (
                            id, user_id, requirement_uuid, snapshot_source,
                            submission_value_kind, submitted_value, outcome,
                            started_at, completed_at, error_code, terminal_source,
                            created_at, updated_at
                        )
                        VALUES (
                            :id, :user_id, :requirement_uuid, 'reconstructed',
                            :value_kind, :submitted_value, 'succeeded',
                            :now, :now, 'verification_succeeded', 'local_seed',
                            :now, :now
                        )
                        """
                    ),
                    {
                        "id": uuid4(),
                        "user_id": user_id,
                        "requirement_uuid": requirement_uuid,
                        "value_kind": value_kind_for_submission_type(
                            requirement.submission_type
                        ).value,
                        "submitted_value": "seeded-local-progress",
                        "now": now,
                    },
                )

            print(
                f"Seeded {len(catalog.active_step_uuids)} steps and "
                f"{len(catalog.active_requirement_uuids)} verifications for "
                f"{github_username}."
            )
    finally:
        await engine.dispose()


if __name__ == "__main__":
    username = sys.argv[1] if len(sys.argv) > 1 else "madebygps"
    asyncio.run(main(username))
