"""Seed all progress data for a user so they can test full completion.

Reads curriculum from the DB (synced from YAML at deploy time) and writes
step_progress + submissions rows so the user shows as fully complete.

Usage: uv run --directory api python ../scripts/seed_progress.py <github_username>
"""

import asyncio
import os
import sys
from datetime import UTC, datetime

from learn_to_cloud_shared.content_service import get_all_phases
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

database_url = os.environ.get(
    "DATABASE__URL", "postgresql+asyncpg://postgres:postgres@db:5432/learn_to_cloud"
)


async def main(github_username: str) -> None:
    engine = create_async_engine(database_url)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_maker() as session:
            phases = await get_all_phases(session)
        if not phases:
            print("ERROR: No curriculum loaded from DB. Run the sync job first.")
            sys.exit(1)
        print(f"Loaded {len(phases)} phases from curriculum DB")

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
                print(f"ERROR: User '{github_username}' not found in the database.")
                print("Make sure you've logged in at least once via the app.")
                sys.exit(1)

            user_id = row.id
            print(f"Found user: {github_username} (id={user_id})")

            now = datetime.now(UTC)

            deleted = await conn.execute(
                text("DELETE FROM step_progress WHERE user_id = :user_id"),
                {"user_id": user_id},
            )
            print(f"Cleaned existing step_progress: {deleted.rowcount}")

            step_count = 0
            for phase in phases:
                for topic in phase.topics:
                    for step in topic.learning_steps:
                        await conn.execute(
                            text(
                                """
                                INSERT INTO step_progress (
                                    user_id, step_uuid, completed_at
                                )
                                VALUES (:user_id, :step_uuid, :completed_at)
                                ON CONFLICT (user_id, step_uuid) DO NOTHING
                                """
                            ),
                            {
                                "user_id": user_id,
                                "step_uuid": step.uuid,
                                "completed_at": now,
                            },
                        )
                        step_count += 1
            print(f"Inserted {step_count} step_progress records")

            sub_count = 0
            for phase in phases:
                if phase.hands_on_verification is None:
                    continue
                for req in phase.hands_on_verification.requirements:
                    sub_type = str(req.submission_type)
                    required_repo = getattr(req, "required_repo", None)
                    # Generate realistic submitted_value per submission type
                    if sub_type == "github_profile":
                        submitted_value = f"https://github.com/{github_username}"
                    elif sub_type == "profile_readme":
                        submitted_value = (
                            f"https://github.com/{github_username}/{github_username}"
                        )
                    elif sub_type == "repo_fork" and required_repo:
                        repo_name = required_repo.split("/")[-1]
                        submitted_value = (
                            f"https://github.com/{github_username}/{repo_name}"
                        )
                    elif sub_type in (
                        "devops_analysis",
                        "security_scanning",
                        "journal_api_verifier",
                    ):
                        submitted_value = (
                            f"https://github.com/{github_username}/journal-starter"
                        )
                    elif sub_type == "pr_review":
                        submitted_value = f"https://seed-data.example.com/{req.slug}"
                    elif sub_type == "deployed_api":
                        submitted_value = "https://journal-api.example.com"
                    else:
                        submitted_value = f"https://seed-data.example.com/{req.slug}"

                    await conn.execute(
                        text(
                            """
                            DELETE FROM submissions
                            WHERE user_id = :user_id
                              AND requirement_uuid = :req_uuid
                            """
                        ),
                        {"user_id": user_id, "req_uuid": req.uuid},
                    )
                    await conn.execute(
                        text(
                            """
                            INSERT INTO submissions (
                                user_id, requirement_uuid, submitted_value,
                                is_validated, validated_at,
                                verification_completed, created_at, updated_at
                            )
                            VALUES (
                                :user_id, :req_uuid, :submitted_value,
                                true, :now, true, :now, :now
                            )
                            """
                        ),
                        {
                            "user_id": user_id,
                            "req_uuid": req.uuid,
                            "submitted_value": submitted_value,
                            "now": now,
                        },
                    )
                    sub_count += 1
            print(f"Inserted {sub_count} submission records")

            print("\nDone! All progress seeded.")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    username = sys.argv[1] if len(sys.argv) > 1 else "madebygps"
    asyncio.run(main(username))
