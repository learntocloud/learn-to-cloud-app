"""Step progress service for learning step management."""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from core.cache import invalidate_progress_cache, update_cached_phase_detail_step
from models import utcnow
from repositories import StepProgressRepository
from repositories.progress_denormalized_repository import UserPhaseProgressRepository
from schemas import StepCompletionResult
from services.content_service import get_topic_by_id

logger = logging.getLogger(__name__)


class StepValidationError(Exception):
    """Raised when step validation fails."""

    pass


class StepAlreadyCompletedError(StepValidationError):
    """Raised when trying to complete an already completed step."""

    def __init__(self, topic_id: str, step_order: int):
        self.topic_id = topic_id
        self.step_order = step_order
        super().__init__(f"Step {step_order} in {topic_id} already completed")


class StepUnknownTopicError(StepValidationError):
    """Raised when a topic_id doesn't exist in content."""

    def __init__(self, topic_id: str):
        self.topic_id = topic_id
        super().__init__(f"Unknown topic_id: {topic_id}")


class StepInvalidStepOrderError(StepValidationError):
    """Raised when step_order is out of range for the topic."""

    def __init__(self, topic_id: str, step_order: int, total_steps: int):
        self.topic_id = topic_id
        self.step_order = step_order
        self.total_steps = total_steps
        super().__init__(
            f"Invalid step_order {step_order} for {topic_id}. "
            f"Must be between 1 and {total_steps}."
        )


class StepInvalidStepIdError(StepValidationError):
    """Raised when a step_id does not exist in the topic."""

    def __init__(self, topic_id: str, step_id: str):
        self.topic_id = topic_id
        self.step_id = step_id
        super().__init__(f"Invalid step_id '{step_id}' for {topic_id}")


def _resolve_total_steps(topic_id: str) -> int:
    """Get total number of learning steps for a topic.

    Args:
        topic_id: The topic ID (e.g., "phase1-topic5")

    Returns:
        Total number of learning steps in the topic

    Raises:
        StepUnknownTopicError: If topic_id doesn't exist in content
    """
    topic = get_topic_by_id(topic_id)
    if topic is None:
        raise StepUnknownTopicError(topic_id)
    return len(topic.learning_steps)


def _resolve_step(topic_id: str, step_id: str) -> tuple[str, int, int]:
    """Resolve and validate a step by stable step id.

    Returns:
        Tuple of (resolved_step_id, step_order, total_steps)
    """
    topic = get_topic_by_id(topic_id)
    if topic is None:
        raise StepUnknownTopicError(topic_id)

    total_steps = len(topic.learning_steps)
    for step in topic.learning_steps:
        if step.id == step_id:
            return step.id, step.order, total_steps

    raise StepInvalidStepIdError(topic_id, step_id)


def parse_phase_id_from_topic_id(topic_id: str) -> int | None:
    """Extract phase ID from a topic_id string (e.g., 'phase1-topic5' -> 1)."""
    if not isinstance(topic_id, str) or not topic_id.startswith("phase"):
        return None
    try:
        return int(topic_id.split("-")[0].replace("phase", ""))
    except (ValueError, IndexError):
        return None


async def get_completed_steps(
    db: AsyncSession,
    user_id: int,
    topic_id: str,
) -> set[str]:
    """Get the set of completed step orders for a user in a topic.

    Thin service wrapper around the repository — keeps routes from
    importing repositories directly.
    """
    step_repo = StepProgressRepository(db)
    return await step_repo.get_completed_step_ids(user_id, topic_id)


async def complete_step(
    db: AsyncSession,
    user_id: int,
    topic_id: str,
    step_id: str,
) -> tuple[StepCompletionResult, set[str]]:
    """Mark a learning step as complete.

    Steps can be completed in any order.

    Args:
        db: Database session
        user_id: The user's ID
        topic_id: The topic ID
        step_id: The stable step identifier to complete

    Returns:
        Tuple of (StepCompletionResult, updated completed step orders)

    Note:
        Idempotent — completing an already-completed step is a no-op
        that returns the current state without error.
    """
    resolved_step_id, step_order, _ = _resolve_step(topic_id, step_id)

    step_repo = StepProgressRepository(db)
    phase_id = parse_phase_id_from_topic_id(topic_id)
    if phase_id is None:
        raise StepUnknownTopicError(topic_id)

    # Atomic check-and-insert: saves 1 round-trip vs exists() + create()
    step_progress = await step_repo.create_if_not_exists(
        user_id=user_id,
        topic_id=topic_id,
        step_id=resolved_step_id,
        step_order=step_order,
        phase_id=phase_id,
    )
    if step_progress is None:
        # Idempotent: already completed is a no-op, not an error.
        # This handles double-clicks, multiple tabs, back-button replays, etc.
        completed_steps = await step_repo.get_completed_step_ids(user_id, topic_id)
        logger.info(
            "step.already_completed",
            extra={
                "user_id": user_id,
                "topic_id": topic_id,
                "step_id": resolved_step_id,
            },
        )
        return StepCompletionResult(
            topic_id=topic_id,
            step_id=resolved_step_id,
            completed_at=utcnow(),
        ), completed_steps

    # Update denormalized progress counts
    denorm_repo = UserPhaseProgressRepository(db)
    await denorm_repo.increment_steps(user_id, phase_id, delta=1)

    # Invalidate cache so dashboard/progress refreshes immediately
    invalidate_progress_cache(user_id)

    from core.metrics import STEP_COMPLETED_COUNTER

    STEP_COMPLETED_COUNTER.add(1, {"phase_id": str(phase_id)})

    logger.info(
        "step.completed",
        extra={
            "user_id": user_id,
            "topic_id": topic_id,
            "step_id": resolved_step_id,
            "step_order": step_order,
        },
    )

    # Fetch updated completed steps in same transaction (avoids re-query in route)
    completed_steps = await step_repo.get_completed_step_ids(user_id, topic_id)

    # Write-through: update phase-detail cache with new completed steps
    if phase_id is not None:
        update_cached_phase_detail_step(user_id, phase_id, topic_id, completed_steps)

    return StepCompletionResult(
        topic_id=step_progress.topic_id,
        step_id=step_progress.step_id,
        completed_at=step_progress.completed_at,
    ), completed_steps


async def uncomplete_step(
    db: AsyncSession,
    user_id: int,
    topic_id: str,
    step_id: str,
) -> tuple[int, set[str]]:
    """Mark a learning step as incomplete (uncomplete it).

    Also removes any steps after this one (cascading uncomplete).

    Args:
        db: Database session
        user_id: The user's ID
        topic_id: The topic ID
        step_id: The stable step identifier to uncomplete

    Returns:
        Tuple of (number of steps deleted, updated completed step orders)

    Raises:
        StepUnknownTopicError: If topic_id doesn't exist in content
        StepInvalidStepOrderError: If step_order is out of range
    """
    _, step_order, _ = _resolve_step(topic_id, step_id)

    step_repo = StepProgressRepository(db)
    deleted = await step_repo.delete_from_step(user_id, topic_id, step_order)

    # Invalidate cache so dashboard/progress refreshes immediately
    if deleted > 0:
        # Recalculate denormalized counts since cascading uncomplete
        # deletes multiple steps
        phase_id = parse_phase_id_from_topic_id(topic_id)

        from core.metrics import STEP_UNCOMPLETED_COUNTER

        STEP_UNCOMPLETED_COUNTER.add(
            deleted,
            {"phase_id": str(phase_id)},
        )

        if phase_id is not None:
            denorm_repo = UserPhaseProgressRepository(db)
            remaining = await step_repo.get_step_counts_by_phase(user_id)
            new_count = remaining.get(phase_id, 0)
            await denorm_repo.recalculate_steps_for_phase(user_id, phase_id, new_count)

        invalidate_progress_cache(user_id)
        logger.info(
            "step.uncompleted",
            extra={
                "user_id": user_id,
                "topic_id": topic_id,
                "step_id": step_id,
                "step_order": step_order,
                "steps_deleted": deleted,
            },
        )

    # Fetch updated completed steps in same transaction
    completed_steps = await step_repo.get_completed_step_ids(user_id, topic_id)

    # Write-through: update phase-detail cache with remaining completed steps
    phase_id = parse_phase_id_from_topic_id(topic_id)
    if phase_id is not None:
        update_cached_phase_detail_step(user_id, phase_id, topic_id, completed_steps)

    return deleted, completed_steps
