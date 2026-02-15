"""Seed all progress data for a user so they can test certificate generation.

Reads topic IDs and step counts directly from the content YAML files to ensure
the seeded data matches exactly what the app expects.

Usage: uv run --directory api python ../scripts/seed_progress.py <github_username>
"""

import asyncio
import sys
from datetime import UTC, datetime
from pathlib import Path

import asyncpg
import yaml

DATABASE_URL = "postgresql://postgres:postgres@localhost:5432/learn_to_cloud"

REPO_ROOT = Path(__file__).resolve().parent.parent
CONTENT_DIR = REPO_ROOT / "content" / "phases"


def load_content() -> (
    tuple[
        dict[int, list[tuple[str, list[str]]]],
        dict[int, list[tuple[str, str, str]]],
    ]
):
    """Load topic IDs, step IDs, and requirements from content YAML files."""
    phase_topics: dict[int, list[tuple[str, list[str]]]] = {}
    phase_requirements: dict[int, list[tuple[str, str, str]]] = {}

    for phase_dir in sorted(CONTENT_DIR.iterdir()):
        if not phase_dir.is_dir() or not phase_dir.name.startswith("phase"):
            continue
        phase_id = int(phase_dir.name.replace("phase", ""))

        phase_meta = phase_dir / "_phase.yaml"
        if phase_meta.exists():
            with open(phase_meta, encoding="utf-8") as f:
                meta = yaml.safe_load(f)
            reqs = []
            hov = meta.get("hands_on_verification", {})
            for req in hov.get("requirements", []):
                reqs.append((
                    req["id"],
                    req["submission_type"],
                    f"https://seed-data.example.com/{req['id']}",
                ))
            phase_requirements[phase_id] = reqs

        topics = []
        for topic_file in sorted(phase_dir.glob("*.yaml")):
            if topic_file.name == "_phase.yaml":
                continue
            with open(topic_file, encoding="utf-8") as f:
                data = yaml.safe_load(f)
            topic_id = data["id"]
            step_ids = [s["id"] for s in data.get("learning_steps", [])]
            topics.append((topic_id, step_ids))
        phase_topics[phase_id] = topics

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
                        user_id, topic_id, step_id, phase_id, step_order, now,
                    )
                    step_count += 1
        print(f"Inserted {step_count} step_progress records")

        sub_count = 0
        for phase_id, requirements in phase_requirements.items():
            for req_id, sub_type, submitted_value in requirements:
                await conn.execute(
                    """
                    INSERT INTO submissions (
                        user_id, requirement_id, attempt_number, submission_type,
                        phase_id, submitted_value, is_validated, validated_at,
                        verification_completed, created_at, updated_at
                    )
                    VALUES ($1, $2, 1, $3, $4, $5, true, $6, true, $6, $6)
                    ON CONFLICT (user_id, requirement_id, attempt_number) DO UPDATE SET
                        is_validated = true,
                        validated_at = $6,
                        verification_completed = true,
                        updated_at = $6
                    """,
                    user_id, req_id, sub_type, phase_id, submitted_value, now,
                )
                sub_count += 1
        print(f"Inserted {sub_count} submission records")

        for phase_id, topics in phase_topics.items():
            total_steps = sum(len(step_ids) for _, step_ids in topics)
            validated_subs = len(phase_requirements.get(phase_id, []))
            await conn.execute(
                """
                INSERT INTO user_phase_progress (
                    user_id,
                    phase_id,
                    completed_steps,
                    validated_submissions,
                    updated_at
                )
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (user_id, phase_id) DO UPDATE SET
                    completed_steps = $3,
                    validated_submissions = $4,
                    updated_at = $5
                """,
                user_id, phase_id, total_steps, validated_subs, now,
            )
        print(f"Updated user_phase_progress for {len(phase_topics)} phases")

        print(
            "\nDone! All progress seeded. You should now be eligible for a certificate."
        )

    finally:
        await conn.close()


if __name__ == "__main__":
    username = sys.argv[1] if len(sys.argv) > 1 else "madebygps"
    asyncio.run(main(username))
