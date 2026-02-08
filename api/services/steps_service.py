"""Step progress service for learning step management."""

from sqlalchemy.ext.asyncio import AsyncSession

from core.cache import invalidate_progress_cache
from repositories import StepProgressRepository
from schemas import StepCompletionResult, StepProgressData
from services.content_service import get_topic_by_id


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


def _parse_phase_id_from_topic_id(topic_id: str) -> int | None:
    if not isinstance(topic_id, str) or not topic_id.startswith("phase"):
        return None
    try:
        return int(topic_id.split("-")[0].replace("phase", ""))
    except (ValueError, IndexError):
        return None


def _validate_step_order(topic_id: str, step_order: int) -> int:
    """Validate step_order is within valid range for the topic.

    Args:
        topic_id: The topic ID (e.g., "phase1-topic5")
        step_order: The step number to validate (1-indexed)

    Returns:
        Total number of steps in the topic (useful for callers)

    Raises:
        StepUnknownTopicError: If topic_id doesn't exist in content
        StepInvalidStepOrderError: If step_order is out of range
    """
    total_steps = _resolve_total_steps(topic_id)
    if step_order < 1 or step_order > total_steps:
        raise StepInvalidStepOrderError(topic_id, step_order, total_steps)
    return total_steps


async def get_topic_step_progress(
    db: AsyncSession,
    user_id: int,
    topic_id: str,
) -> StepProgressData:
    """Get the step progress for a topic.

    Args:
        db: Database session
        user_id: The user's ID
        topic_id: The topic ID (e.g., "phase1-topic5")

    Returns:
        StepProgressData with completed steps

    Raises:
        StepUnknownTopicError: If topic_id doesn't exist in content
    """
    total_steps = _resolve_total_steps(topic_id)

    step_repo = StepProgressRepository(db)
    completed_step_orders = await step_repo.get_completed_step_orders(user_id, topic_id)
    completed_steps = sorted(completed_step_orders)

    return StepProgressData(
        topic_id=topic_id,
        completed_steps=completed_steps,
        total_steps=total_steps,
    )


async def get_completed_steps(
    db: AsyncSession,
    user_id: int,
    topic_id: str,
) -> set[int]:
    """Get the set of completed step orders for a user in a topic.

    Thin service wrapper around the repository — keeps routes from
    importing repositories directly.
    """
    step_repo = StepProgressRepository(db)
    return await step_repo.get_completed_step_orders(user_id, topic_id)


async def complete_step(
    db: AsyncSession,
    user_id: int,
    topic_id: str,
    step_order: int,
) -> StepCompletionResult:
    """Mark a learning step as complete.

    Steps can be completed in any order.

    Args:
        db: Database session
        user_id: The user's ID
        topic_id: The topic ID
        step_order: The step number to complete

    Returns:
        StepCompletionResult with completion details

    Raises:
        StepAlreadyCompletedError: If step is already completed
    """
    _validate_step_order(topic_id, step_order)

    step_repo = StepProgressRepository(db)

    # Atomic check-and-insert: saves 1 round-trip vs exists() + create()
    step_progress = await step_repo.create_if_not_exists(
        user_id=user_id,
        topic_id=topic_id,
        step_order=step_order,
    )
    if step_progress is None:
        raise StepAlreadyCompletedError(topic_id, step_order)

    # Invalidate cache so dashboard/progress refreshes immediately
    invalidate_progress_cache(user_id)

    return StepCompletionResult(
        topic_id=step_progress.topic_id,
        step_order=step_progress.step_order,
        completed_at=step_progress.completed_at,
    )


async def uncomplete_step(
    db: AsyncSession,
    user_id: int,
    topic_id: str,
    step_order: int,
) -> int:
    """Mark a learning step as incomplete (uncomplete it).

    Also removes any steps after this one (cascading uncomplete).

    Args:
        db: Database session
        user_id: The user's ID
        topic_id: The topic ID
        step_order: The step number to uncomplete

    Returns:
        Number of steps deleted

    Raises:
        StepUnknownTopicError: If topic_id doesn't exist in content
        StepInvalidStepOrderError: If step_order is out of range
    """
    _validate_step_order(topic_id, step_order)

    step_repo = StepProgressRepository(db)
    deleted = await step_repo.delete_from_step(user_id, topic_id, step_order)

    # Invalidate cache so dashboard/progress refreshes immediately
    if deleted > 0:
        invalidate_progress_cache(user_id)

    return deleted
