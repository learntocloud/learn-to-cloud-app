#!/usr/bin/env python
"""Seed the local database with test data for trend analysis.

Creates users and activities spread across multiple days to test
the metrics aggregation and trends API.

Usage:
    # Seed with default settings (50 users, 60 days)
    cd api && source .env && uv run python scripts/seed_trend_data.py

    # Custom user count and date range
    uv run python scripts/seed_trend_data.py --users 100 --days 90

    # Clear existing seed data first
    uv run python scripts/seed_trend_data.py --clear

After seeding, run aggregation:
    uv run python scripts/aggregate_metrics.py --backfill --start 2025-12-01

Then check trends at:
    GET http://localhost:8000/api/admin/trends?days=60
"""

import argparse
import asyncio
import random
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

# Add api directory to path for imports
api_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(api_dir))

from faker import Faker
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import create_engine, create_session_maker, dispose_engine
from core.logger import configure_logging, get_logger
from models import (
    ActivityType,
    Certificate,
    QuestionAttempt,
    StepProgress,
    Submission,
    SubmissionType,
    User,
    UserActivity,
)

configure_logging()
logger = get_logger(__name__)
fake = Faker()

# Seed prefix to identify test data
SEED_PREFIX = "seed_"


def generate_user_id() -> str:
    """Generate a Clerk-style user ID with seed prefix."""
    return f"{SEED_PREFIX}user_{fake.uuid4().replace('-', '')[:20]}"


def random_datetime_on_date(target_date: date) -> datetime:
    """Generate a random datetime on the given date."""
    hour = random.randint(6, 23)  # Activity between 6am-11pm
    minute = random.randint(0, 59)
    second = random.randint(0, 59)
    return datetime(
        target_date.year,
        target_date.month,
        target_date.day,
        hour,
        minute,
        second,
        tzinfo=UTC,
    )


async def clear_seed_data(db: AsyncSession) -> dict[str, int]:
    """Remove all seeded test data (users with seed_ prefix)."""
    counts = {}

    # Delete users with seed prefix (cascades to related tables)
    result = await db.execute(delete(User).where(User.id.like(f"{SEED_PREFIX}%")))
    counts["users"] = result.rowcount

    await db.commit()
    return counts


async def seed_users(db: AsyncSession, num_users: int, days: int) -> list[User]:
    """Create users with signup dates spread across the date range."""
    users = []
    today = datetime.now(UTC).date()
    start_date = today - timedelta(days=days)

    # Distribution: more recent signups (exponential decay)
    for i in range(num_users):
        # Bias toward recent dates using exponential distribution
        days_ago = int(random.expovariate(1 / (days / 3)))
        days_ago = min(days_ago, days - 1)  # Clamp to range
        signup_date = today - timedelta(days=days_ago)
        signup_dt = random_datetime_on_date(signup_date)

        user = User(
            id=generate_user_id(),
            email=fake.unique.email(),
            first_name=fake.first_name(),
            last_name=fake.last_name(),
            avatar_url=f"https://avatars.githubusercontent.com/u/{fake.random_int(1, 99999)}",
            github_username=f"{SEED_PREFIX}{fake.unique.user_name()[:30]}",
            is_admin=False,
            created_at=signup_dt,
            updated_at=signup_dt,
        )
        db.add(user)
        users.append(user)

    await db.flush()
    logger.info("users.seeded", count=len(users))
    return users


async def seed_activities(
    db: AsyncSession, users: list[User], days: int
) -> dict[str, int]:
    """Generate activities for users across the date range."""
    counts = {
        "steps": 0,
        "questions_attempted": 0,
        "questions_passed": 0,
        "submissions": 0,
        "activities": 0,
        "certificates": 0,
        "phases": 0,
    }

    today = datetime.now(UTC).date()
    phase_ids = [0, 1, 2, 3, 4, 5]
    topics_per_phase = 3
    steps_per_topic = 5

    for user in users:
        signup_date = user.created_at.date()
        days_active = (today - signup_date).days + 1

        # Skip if user just signed up
        if days_active < 1:
            continue

        # Determine user engagement level (1-10)
        engagement = random.randint(1, 10)

        # Generate activities for random days since signup
        active_days_count = min(days_active, max(1, engagement * 3))
        active_dates = random.sample(
            [signup_date + timedelta(days=d) for d in range(days_active)],
            k=min(active_days_count, days_active),
        )

        # Track user's progress through phases
        current_phase = 0
        completed_topics = set()
        completed_steps = set()

        for activity_date in sorted(active_dates):
            activity_dt = random_datetime_on_date(activity_date)

            # Number of activities this day based on engagement
            activities_today = random.randint(1, engagement)

            for _ in range(activities_today):
                # Choose activity type based on progression
                activity_type = random.choices(
                    [
                        ActivityType.STEP_COMPLETE,
                        ActivityType.QUESTION_ATTEMPT,
                        ActivityType.HANDS_ON_VALIDATED,
                    ],
                    weights=[60, 30, 10],  # Steps most common
                )[0]

                phase_id = min(current_phase, len(phase_ids) - 1)
                topic_num = random.randint(1, topics_per_phase)
                topic_id = f"phase{phase_id}-topic{topic_num}"

                if activity_type == ActivityType.STEP_COMPLETE:
                    step_order = random.randint(1, steps_per_topic)
                    step_key = f"{user.id}:{topic_id}:{step_order}"

                    if step_key not in completed_steps:
                        completed_steps.add(step_key)

                        step = StepProgress(
                            user_id=user.id,
                            topic_id=topic_id,
                            step_order=step_order,
                            completed_at=activity_dt,
                        )
                        db.add(step)
                        counts["steps"] += 1

                        activity = UserActivity(
                            user_id=user.id,
                            activity_type=ActivityType.STEP_COMPLETE,
                            activity_date=activity_date,
                            reference_id=topic_id,
                            created_at=activity_dt,
                        )
                        db.add(activity)
                        counts["activities"] += 1

                elif activity_type == ActivityType.QUESTION_ATTEMPT:
                    question_id = f"{topic_id}-q{random.randint(1, 3)}"
                    is_passed = random.random() < 0.7  # 70% pass rate

                    attempt = QuestionAttempt(
                        user_id=user.id,
                        topic_id=topic_id,
                        question_id=question_id,
                        user_answer=fake.paragraph(nb_sentences=3),
                        is_passed=is_passed,
                        llm_feedback="Great answer!" if is_passed else "Try again.",
                        confidence_score=random.uniform(0.6, 1.0)
                        if is_passed
                        else random.uniform(0.3, 0.6),
                        created_at=activity_dt,
                    )
                    db.add(attempt)
                    counts["questions_attempted"] += 1
                    if is_passed:
                        counts["questions_passed"] += 1

                    activity = UserActivity(
                        user_id=user.id,
                        activity_type=ActivityType.QUESTION_ATTEMPT,
                        activity_date=activity_date,
                        reference_id=question_id,
                        created_at=activity_dt,
                    )
                    db.add(activity)
                    counts["activities"] += 1

                    # Mark topic complete occasionally
                    if is_passed and random.random() < 0.2:
                        completed_topics.add(topic_id)

                elif activity_type == ActivityType.HANDS_ON_VALIDATED:
                    requirement_id = f"phase{phase_id}-hands-on-1"
                    sub_key = f"{user.id}:{requirement_id}"

                    # Only create one submission per requirement
                    if sub_key not in completed_steps:
                        completed_steps.add(sub_key)

                        submission = Submission(
                            user_id=user.id,
                            requirement_id=requirement_id,
                            submission_type=SubmissionType.GITHUB_PROFILE,
                            phase_id=phase_id,
                            submitted_value=f"https://github.com/{user.github_username}",
                            extracted_username=user.github_username,
                            is_validated=True,
                            validated_at=activity_dt,
                            verification_completed=True,
                            created_at=activity_dt,
                            updated_at=activity_dt,
                        )
                        db.add(submission)
                        counts["submissions"] += 1

                        activity = UserActivity(
                            user_id=user.id,
                            activity_type=ActivityType.HANDS_ON_VALIDATED,
                            activity_date=activity_date,
                            reference_id=requirement_id,
                            created_at=activity_dt,
                        )
                        db.add(activity)
                        counts["activities"] += 1

            # Chance to complete phase and advance
            if len(completed_topics) >= topics_per_phase and random.random() < 0.3:
                phase_activity = UserActivity(
                    user_id=user.id,
                    activity_type=ActivityType.PHASE_COMPLETE,
                    activity_date=activity_date,
                    reference_id=f"phase{current_phase}",
                    created_at=activity_dt,
                )
                db.add(phase_activity)
                counts["phases"] += 1
                counts["activities"] += 1

                current_phase += 1
                completed_topics.clear()

        # Award certificate to high-engagement users who completed phases
        if engagement >= 7 and current_phase >= 2:
            cert_dt = random_datetime_on_date(
                min(today, signup_date + timedelta(days=days_active - 1))
            )
            cert = Certificate(
                user_id=user.id,
                certificate_type="phase_completion",
                verification_code=fake.sha256()[:64],
                recipient_name=f"{user.first_name} {user.last_name}",
                issued_at=cert_dt,
                phases_completed=current_phase,
                total_phases=len(phase_ids),
                created_at=cert_dt,
                updated_at=cert_dt,
            )
            db.add(cert)
            counts["certificates"] += 1

            activity = UserActivity(
                user_id=user.id,
                activity_type=ActivityType.CERTIFICATE_EARNED,
                activity_date=cert_dt.date(),
                reference_id=cert.certificate_type,
                created_at=cert_dt,
            )
            db.add(activity)
            counts["activities"] += 1

    await db.flush()
    return counts


async def main() -> None:
    """Seed database with test data for trend analysis."""
    parser = argparse.ArgumentParser(description="Seed trend test data")
    parser.add_argument(
        "--users",
        type=int,
        default=50,
        help="Number of users to create (default: 50)",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=60,
        help="Days of history to generate (default: 60)",
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Clear existing seed data before seeding",
    )
    args = parser.parse_args()

    engine = create_engine()
    session_maker = create_session_maker(engine)

    try:
        async with session_maker() as db:
            if args.clear:
                logger.info("clearing.seed_data")
                cleared = await clear_seed_data(db)
                logger.info("cleared.seed_data", **cleared)

            logger.info(
                "seeding.start",
                users=args.users,
                days=args.days,
            )

            users = await seed_users(db, args.users, args.days)
            counts = await seed_activities(db, users, args.days)

            await db.commit()

            logger.info("seeding.complete", users=len(users), **counts)

            # Print summary
            print("\n" + "=" * 50)
            print("SEED DATA SUMMARY")
            print("=" * 50)
            print(f"Users created:        {len(users)}")
            print(f"Steps completed:      {counts['steps']}")
            print(f"Questions attempted:  {counts['questions_attempted']}")
            print(f"Questions passed:     {counts['questions_passed']}")
            print(f"Submissions:          {counts['submissions']}")
            print(f"Phases completed:     {counts['phases']}")
            print(f"Certificates:         {counts['certificates']}")
            print(f"Total activities:     {counts['activities']}")
            print("=" * 50)
            print("\nNext steps:")
            print("1. Run aggregation:")
            today = datetime.now(UTC).date()
            start = today - timedelta(days=args.days)
            print(
                f"   uv run python scripts/aggregate_metrics.py "
                f"--backfill --start {start.isoformat()} --end {today.isoformat()}"
            )
            print("\n2. Check trends endpoint:")
            print(f"   curl http://localhost:8000/api/admin/trends?days={args.days}")
            print()

    finally:
        await dispose_engine(engine)


if __name__ == "__main__":
    asyncio.run(main())
