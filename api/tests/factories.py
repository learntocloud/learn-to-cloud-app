"""Factory Boy factories for generating test data.

Factories provide a clean way to create test objects with sensible defaults.
Override specific fields as needed in tests.

Usage:
    # Create a user
    user = UserFactory.build()  # In-memory only
    user = await UserFactory.create_async(db_session)  # Persisted

    # Override fields
    user = UserFactory.build(email="custom@example.com")

    # Create related objects
    submission = SubmissionFactory.build(user_id=user.id)
"""

import random
from datetime import UTC, date, datetime, timedelta
from functools import cache

import factory
from faker import Faker
from sqlalchemy.ext.asyncio import AsyncSession

from models import (
    ActivityType,
    Certificate,
    ProcessedWebhook,
    StepProgress,
    Submission,
    SubmissionType,
    User,
    UserActivity,
)

fake = Faker()


@cache
def _get_valid_phase_ids() -> list[int]:
    """Return valid phase IDs from content, with a safe fallback.

    Uses a lazy import to avoid content I/O at module import time.
    """
    try:
        from services.progress_service import get_all_phase_ids
    except Exception:
        return [0, 1, 2, 3, 4, 5]

    try:
        return get_all_phase_ids()
    except Exception:
        return [0, 1, 2, 3, 4, 5]


def _get_random_phase_id() -> int:
    """Select a valid phase ID for test data."""
    return random.choice(_get_valid_phase_ids())


def _parse_phase_id_from_topic_id(topic_id: str) -> int:
    if not isinstance(topic_id, str) or not topic_id.startswith("phase"):
        return _get_random_phase_id()
    try:
        return int(topic_id.split("-")[0].replace("phase", ""))
    except (ValueError, IndexError):
        return _get_random_phase_id()


# =============================================================================
# Async Factory Helpers
# =============================================================================


async def create_async(
    factory_class: type[factory.Factory], db: AsyncSession, **kwargs
):
    """Create an instance using a factory and persist to database.

    Usage:
        user = await create_async(UserFactory, db_session, email="test@example.com")
    """
    instance = factory_class.build(**kwargs)
    db.add(instance)
    await db.flush()
    await db.refresh(instance)
    return instance


async def create_batch_async(
    factory_class: type[factory.Factory], db: AsyncSession, size: int, **kwargs
):
    """Create multiple instances and persist to database."""
    instances = factory_class.build_batch(size, **kwargs)
    for instance in instances:
        db.add(instance)
    await db.flush()
    for instance in instances:
        await db.refresh(instance)
    return instances


# =============================================================================
# User Factory
# =============================================================================


class UserFactory(factory.Factory):
    """Factory for creating User instances."""

    class Meta:
        model = User

    # Clerk-style user ID
    id = factory.LazyFunction(lambda: f"user_{fake.uuid4().replace('-', '')[:24]}")
    email = factory.LazyAttribute(lambda _: fake.email())
    first_name = factory.LazyAttribute(lambda _: fake.first_name())
    last_name = factory.LazyAttribute(lambda _: fake.last_name())
    avatar_url = factory.LazyAttribute(
        lambda _: f"https://avatars.githubusercontent.com/u/{fake.random_int(1, 9999)}"
    )
    github_username = factory.LazyAttribute(
        lambda _: fake.user_name().lower()[:39]  # GitHub max is 39 chars
    )
    is_admin = False
    created_at = factory.LazyFunction(lambda: datetime.now(UTC))
    updated_at = factory.LazyFunction(lambda: datetime.now(UTC))


class PlaceholderUserFactory(UserFactory):
    """Factory for creating placeholder users (pre-Clerk sync)."""

    email = factory.LazyAttribute(lambda obj: f"{obj.id}@placeholder.local")
    first_name = None
    last_name = None
    avatar_url = None
    github_username = None


class AdminUserFactory(UserFactory):
    """Factory for creating admin users."""

    is_admin = True


# =============================================================================
# Submission Factory
# =============================================================================


class SubmissionFactory(factory.Factory):
    """Factory for creating Submission instances."""

    class Meta:
        model = Submission

    # Let DB assign autoincrement ID
    user_id = factory.LazyAttribute(
        lambda _: f"user_{fake.uuid4().replace('-', '')[:24]}"
    )
    requirement_id = factory.LazyAttribute(
        lambda _: f"phase{_get_random_phase_id()}-hands-on-{fake.random_int(1, 5)}"
    )
    submission_type = SubmissionType.GITHUB_PROFILE
    phase_id = factory.LazyAttribute(lambda _: _get_random_phase_id())
    submitted_value = factory.LazyAttribute(
        lambda _: f"https://github.com/{fake.user_name()}"
    )
    extracted_username = factory.LazyAttribute(lambda _: fake.user_name().lower())
    is_validated = True
    validated_at = factory.LazyFunction(lambda: datetime.now(UTC))
    created_at = factory.LazyFunction(lambda: datetime.now(UTC))
    updated_at = factory.LazyFunction(lambda: datetime.now(UTC))


class UnvalidatedSubmissionFactory(SubmissionFactory):
    """Factory for creating unvalidated submissions."""

    is_validated = False
    validated_at = None


# =============================================================================
# Activity Factory
# =============================================================================


class UserActivityFactory(factory.Factory):
    """Factory for creating UserActivity instances."""

    class Meta:
        model = UserActivity

    # Let DB assign autoincrement ID
    user_id = factory.LazyAttribute(
        lambda _: f"user_{fake.uuid4().replace('-', '')[:24]}"
    )
    activity_type = ActivityType.STEP_COMPLETE
    activity_date = factory.LazyFunction(lambda: date.today())
    reference_id = factory.LazyAttribute(
        lambda _: f"phase{_get_random_phase_id()}-topic{fake.random_int(1, 5)}"
    )
    created_at = factory.LazyFunction(lambda: datetime.now(UTC))


class StreakActivityFactory(UserActivityFactory):
    """Factory for creating activities with consecutive dates (for streak testing)."""

    @classmethod
    def create_streak(cls, user_id: str, days: int, start_date: date | None = None):
        """Create a streak of consecutive daily activities.

        Args:
            user_id: The user's ID
            days: Number of consecutive days
            start_date: Starting date (defaults to today)

        Returns:
            List of UserActivity instances (not persisted)
        """
        if start_date is None:
            start_date = date.today()

        activities = []
        for i in range(days):
            activity_date = start_date - timedelta(days=i)
            activities.append(
                cls.build(
                    user_id=user_id,
                    activity_date=activity_date,
                    created_at=datetime.combine(
                        activity_date, datetime.min.time()
                    ).replace(tzinfo=UTC),
                )
            )
        return activities


# =============================================================================
# Progress Factories
# =============================================================================


class StepProgressFactory(factory.Factory):
    """Factory for creating StepProgress instances."""

    class Meta:
        model = StepProgress

    # Let DB assign autoincrement ID
    user_id = factory.LazyAttribute(
        lambda _: f"user_{fake.uuid4().replace('-', '')[:24]}"
    )
    topic_id = factory.LazyAttribute(
        lambda _: f"phase{_get_random_phase_id()}-topic{fake.random_int(1, 5)}"
    )
    phase_id = factory.LazyAttribute(
        lambda obj: _parse_phase_id_from_topic_id(obj.topic_id)
    )
    step_order = factory.Sequence(lambda n: n + 1)
    completed_at = factory.LazyFunction(lambda: datetime.now(UTC))


# =============================================================================
# Certificate Factory
# =============================================================================


class CertificateFactory(factory.Factory):
    """Factory for creating Certificate instances."""

    class Meta:
        model = Certificate

    # Let DB assign autoincrement ID
    user_id = factory.LazyAttribute(
        lambda _: f"user_{fake.uuid4().replace('-', '')[:24]}"
    )
    certificate_type = "phase_completion"
    verification_code = factory.LazyFunction(lambda: fake.sha256()[:64])
    recipient_name = factory.LazyAttribute(
        lambda _: f"{fake.first_name()} {fake.last_name()}"
    )
    issued_at = factory.LazyFunction(lambda: datetime.now(UTC))
    phases_completed = factory.LazyAttribute(lambda _: fake.random_int(1, 5))
    total_phases = 5
    created_at = factory.LazyFunction(lambda: datetime.now(UTC))
    updated_at = factory.LazyFunction(lambda: datetime.now(UTC))


# =============================================================================
# Webhook Factory
# =============================================================================


class ProcessedWebhookFactory(factory.Factory):
    """Factory for creating ProcessedWebhook instances."""

    class Meta:
        model = ProcessedWebhook

    id = factory.LazyFunction(lambda: f"evt_{fake.uuid4().replace('-', '')[:24]}")
    event_type = factory.LazyAttribute(
        lambda _: fake.random_element(["user.created", "user.updated", "user.deleted"])
    )
    processed_at = factory.LazyFunction(lambda: datetime.now(UTC))
