"""Seed all progress data for a user so they can test full completion.

Reads topic IDs and step counts directly from the content YAML files to ensure
the seeded data matches exactly what the app expects.

Usage: uv run --directory api python ../scripts/seed_progress.py <github_username>
"""

import asyncio
import os
import sys
from datetime import UTC, datetime

import asyncpg

from learn_to_cloud_shared.content_service import get_all_phases

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://postgres:postgres@db:5432/learn_to_cloud"
)


def load_content() -> tuple[
    dict[int, list[tuple[str, list[str]]]],
    dict[int, list[dict[str, str | None]]],
]:
    """Load topic IDs, step IDs, and requirements from packaged content."""
    phase_topics: dict[int, list[tuple[str, list[str]]]] = {}
    phase_requirements: dict[int, list[dict[str, str | None]]] = {}

    for phase in get_all_phases():
        phase_topics[phase.id] = [
            (topic.id, [step.id for step in topic.learning_steps])
            for topic in phase.topics
        ]

        if phase.hands_on_verification:
            phase_requirements[phase.id] = [
                {
                    "id": req.id,
                    "submission_type": str(req.submission_type),
                    "required_repo": req.required_repo,
                }
                for req in phase.hands_on_verification.requirements
            ]

    return phase_topics, phase_requirements


async def main(github_username: str) -> None:
    phase_topics, phase_requirements = load_content()
    print(f"Loaded {len(phase_topics)} phases from content YAML")

    conn = await asyncpg.connect(DATABASE_URL)
    try:
        user = await conn.fetchrow(
            "SELECT id, github_username FROM users WHERE github_username = $1",
            github_username,
        )
        if not user:
            print(f"ERROR: User '{github_username}' not found in the database.")
            print("Make sure you've logged in at least once via the app.")
            sys.exit(1)

        user_id = user["id"]
        print(f"Found user: {github_username} (id={user_id})")

        now = datetime.now(UTC)

        deleted = await conn.execute(
            "DELETE FROM step_progress WHERE user_id = $1", user_id
        )
        print(f"Cleaned existing step_progress: {deleted}")

        step_count = 0
        for phase_id, topics in phase_topics.items():
            for topic_id, step_ids in topics:
                for step_order, step_id in enumerate(step_ids, 1):
                    await conn.execute(
                        """
                        INSERT INTO step_progress (
                            user_id,
                            topic_id,
                            step_id,
                            phase_id,
                            step_order,
                            completed_at
                        )
                        VALUES ($1, $2, $3, $4, $5, $6)
                        ON CONFLICT (user_id, topic_id, step_id) DO NOTHING
                        """,
                        user_id,
                        topic_id,
                        step_id,
                        phase_id,
                        step_order,
                        now,
                    )
                    step_count += 1
        print(f"Inserted {step_count} step_progress records")

        sub_count = 0
        for phase_id, requirements in phase_requirements.items():
            for req in requirements:
                req_id = req["id"]
                sub_type = req["submission_type"]
                # Generate realistic submitted_value per submission type
                if sub_type == "github_profile":
                    submitted_value = f"https://github.com/{github_username}"
                elif sub_type == "profile_readme":
                    submitted_value = (
                        f"https://github.com/{github_username}/{github_username}"
                    )
                elif sub_type == "repo_fork" and req.get("required_repo"):
                    repo_name = req["required_repo"].split("/")[-1]
                    submitted_value = (
                        f"https://github.com/{github_username}/{repo_name}"
                    )
                elif sub_type in (
                    "devops_analysis",
                    "security_scanning",
                    "ci_status",
                ):
                    submitted_value = (
                        f"https://github.com/{github_username}/journal-starter"
                    )
                elif sub_type == "pr_review":
                    submitted_value = f"https://seed-data.example.com/{req_id}"
                elif sub_type == "deployed_api":
                    submitted_value = "https://journal-api.example.com"
                else:
                    submitted_value = f"https://seed-data.example.com/{req_id}"
                await conn.execute(
                    """
                    INSERT INTO submissions (
                        user_id, requirement_id, attempt_number, submission_type,
                        phase_id, submitted_value, is_validated, validated_at,
                        verification_completed, created_at, updated_at
                    )
                    VALUES ($1, $2, 1, $3, $4, $5, true, $6, true, $6, $6)
                    ON CONFLICT (user_id, requirement_id, attempt_number) DO UPDATE SET
                        submitted_value = $5,
                        is_validated = true,
                        validated_at = $6,
                        verification_completed = true,
                        updated_at = $6
                    """,
                    user_id,
                    req_id,
                    sub_type,
                    phase_id,
                    submitted_value,
                    now,
                )
                sub_count += 1
        print(f"Inserted {sub_count} submission records")

        print("\nDone! All progress seeded. You should now show as fully complete.")

    finally:
        await conn.close()


if __name__ == "__main__":
    username = sys.argv[1] if len(sys.argv) > 1 else "madebygps"
    asyncio.run(main(username))
