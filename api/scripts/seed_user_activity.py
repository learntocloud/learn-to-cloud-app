"""Seed local DB with activity/progress data for a single user.

This script is intended for local performance testing and EXPLAIN plans.
It creates a user (if missing) and inserts activities, step progress,
and submissions.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import delete, insert, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from core.database import create_engine, create_session_maker, dispose_engine
from models import (
    ActivityType,
    Certificate,
    StepProgress,
    Submission,
    SubmissionType,
    User,
    UserActivity,
    UserPhaseProgress,
)

DEFAULT_USER_ID = "madebygps"
DEFAULT_SEED = 42
DEFAULT_ACTIVITY_MULTIPLIER = 1


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed local DB with activity data")
    parser.add_argument("--user-id", default=DEFAULT_USER_ID)
    parser.add_argument(
        "--activities",
        type=int,
        default=None,
        help="Override activity count (default derives from content)",
    )
    parser.add_argument(
        "--steps",
        type=int,
        default=None,
        help="Override step progress count (default uses content total)",
    )
    parser.add_argument(
        "--submissions",
        type=int,
        default=None,
        help="Override submission count (default uses content total)",
    )
    parser.add_argument(
        "--activity-multiplier",
        type=int,
        default=DEFAULT_ACTIVITY_MULTIPLIER,
        help="Multiplier for activity rows based on total events (default 1x)",
    )
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)

    wipe_group = parser.add_mutually_exclusive_group()
    wipe_group.add_argument(
        "--wipe",
        dest="wipe",
        action="store_true",
        help="Delete existing user data before seeding (default)",
    )
    wipe_group.add_argument(
        "--no-wipe",
        dest="wipe",
        action="store_false",
        help="Keep existing user data (best-effort inserts)",
    )
    parser.set_defaults(wipe=True)

    return parser.parse_args()


def _chunked(items: list[dict], chunk_size: int) -> Iterable[list[dict]]:
    for i in range(0, len(items), chunk_size):
        yield items[i : i + chunk_size]


async def _insert_chunks(
    session, stmt, rows: list[dict], chunk_size: int = 1000
) -> int:
    inserted = 0
    for chunk in _chunked(rows, chunk_size):
        await session.execute(stmt, chunk)
        inserted += len(chunk)
    return inserted


def _parse_phase_id(value: str) -> int:
    return int(value.replace("phase", ""))


def _load_content() -> tuple[list[dict], list[dict]]:
    root = Path(__file__).resolve().parents[2]
    phases_dir = root / "frontend" / "public" / "content" / "phases"
    index_paths = sorted(phases_dir.glob("phase*/index.json"))
    if not index_paths:
        raise FileNotFoundError("No phase index files found")

    topics: list[dict] = []
    requirements: list[dict] = []

    for index_path in index_paths:
        phase = json.loads(index_path.read_text(encoding="utf-8"))
        phase_id = phase.get("id")
        topic_slugs = phase.get("topics", [])
        for requirement in phase.get("hands_on_verification", {}).get(
            "requirements", []
        ):
            requirement_copy = dict(requirement)
            requirement_copy["phase_id"] = phase_id
            requirements.append(requirement_copy)

        for slug in topic_slugs:
            topic_path = index_path.parent / f"{slug}.json"
            topic = json.loads(topic_path.read_text(encoding="utf-8"))
            topics.append(topic)

    return topics, requirements


async def _run(args: argparse.Namespace) -> None:
    rng = random.Random(args.seed)
    now = datetime.now(UTC)

    engine = create_engine()
    session_maker = create_session_maker(engine)

    topics, requirements = _load_content()

    steps_pool = [
        (topic["id"], step["order"], _parse_phase_id(topic["id"].split("-")[0]))
        for topic in topics
        for step in topic.get("learning_steps", [])
    ]
    steps_to_insert = args.steps if args.steps is not None else len(steps_pool)
    submissions_to_insert = (
        args.submissions if args.submissions is not None else len(requirements)
    )
    activity_target = args.activities

    async with session_maker() as session:
        if args.wipe:
            await session.execute(
                delete(Submission).where(Submission.user_id == args.user_id)
            )
            await session.execute(
                delete(StepProgress).where(StepProgress.user_id == args.user_id)
            )
            await session.execute(
                delete(UserActivity).where(UserActivity.user_id == args.user_id)
            )
            await session.execute(
                delete(UserPhaseProgress).where(
                    UserPhaseProgress.user_id == args.user_id
                )
            )
            await session.execute(
                delete(Certificate).where(Certificate.user_id == args.user_id)
            )

        existing = await session.execute(
            select(User.id, User.github_username).where(
                or_(User.id == args.user_id, User.github_username == args.user_id)
            )
        )
        existing_rows = existing.all()
        user_id_exists = any(row.id == args.user_id for row in existing_rows)
        github_in_use = any(
            row.github_username == args.user_id for row in existing_rows
        )

        if not user_id_exists:
            github_username = args.user_id if not github_in_use else None
            user_stmt = (
                pg_insert(User)
                .values(
                    id=args.user_id,
                    email=f"{args.user_id}@example.com",
                    first_name="Made",
                    last_name="ByGPS",
                    github_username=github_username,
                )
                .on_conflict_do_nothing(index_elements=["id"])
            )
            await session.execute(user_stmt)

        step_rows: list[dict] = []
        rng.shuffle(steps_pool)
        for topic_id, step_order, phase_id in steps_pool[:steps_to_insert]:
            completed_at = now - timedelta(days=rng.randint(0, 180))
            step_rows.append(
                {
                    "user_id": args.user_id,
                    "topic_id": topic_id,
                    "phase_id": phase_id,
                    "step_order": step_order,
                    "completed_at": completed_at,
                }
            )

        submission_rows: list[dict] = []
        if submissions_to_insert > len(requirements):
            submissions_to_insert = len(requirements)
        rng.shuffle(requirements)
        for i, requirement in enumerate(requirements[:submissions_to_insert]):
            phase_id = requirement.get("phase_id", 0)
            requirement_id = requirement.get("id", f"phase{phase_id}-req{i + 1}")
            submission_type = SubmissionType(requirement.get("submission_type"))
            is_validated = rng.random() < 0.5
            validated_at = now if is_validated else None
            submission_rows.append(
                {
                    "user_id": args.user_id,
                    "requirement_id": requirement_id,
                    "submission_type": submission_type,
                    "phase_id": phase_id,
                    "submitted_value": f"seed-value-{i}",
                    "extracted_username": args.user_id,
                    "is_validated": is_validated,
                    "validated_at": validated_at,
                    "verification_completed": True,
                    "feedback_json": None,
                    "created_at": now,
                    "updated_at": now,
                }
            )

        if activity_target is None:
            activity_target = (
                len(step_rows) + len(submission_rows)
            ) * args.activity_multiplier

        activity_rows: list[dict] = []
        activity_types = list(ActivityType)
        for i in range(activity_target):
            days_ago = rng.randint(0, 364)
            activity_date = (now - timedelta(days=days_ago)).date()
            created_at = now - timedelta(days=days_ago, minutes=rng.randint(0, 1440))
            activity_rows.append(
                {
                    "user_id": args.user_id,
                    "activity_type": rng.choice(activity_types),
                    "activity_date": activity_date,
                    "reference_id": f"seed-{i}",
                    "created_at": created_at,
                }
            )

        inserted_activities = await _insert_chunks(
            session, insert(UserActivity), activity_rows
        )
        inserted_steps = await _insert_chunks(
            session,
            pg_insert(StepProgress).on_conflict_do_nothing(
                index_elements=["user_id", "topic_id", "step_order"]
            ),
            step_rows,
        )

        submission_stmt = pg_insert(Submission).on_conflict_do_update(
            index_elements=["user_id", "requirement_id"],
            set_={
                "submission_type": Submission.submission_type,
                "phase_id": Submission.phase_id,
                "submitted_value": Submission.submitted_value,
                "extracted_username": Submission.extracted_username,
                "is_validated": Submission.is_validated,
                "validated_at": Submission.validated_at,
                "verification_completed": Submission.verification_completed,
                "feedback_json": Submission.feedback_json,
                "updated_at": Submission.updated_at,
            },
        )
        inserted_submissions = await _insert_chunks(
            session, submission_stmt, submission_rows
        )

        await session.commit()

    await dispose_engine(engine)

    print("Seed complete")
    print(f"User: {args.user_id}")
    print(f"Activities inserted: {inserted_activities}")
    print(f"Step progress inserted: {inserted_steps}")
    print(f"Submissions inserted: {inserted_submissions}")


def main() -> None:
    args = _parse_args()
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
