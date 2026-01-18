"""Step progress service for learning step management."""

from dataclasses import dataclass
from datetime import UTC, datetime

from core.cache import invalidate_progress_cache
from core.telemetry import add_custom_attribute, log_metric, track_operation
from models import ActivityType
from repositories import ActivityRepository, StepProgressRepository
from services.content_service import get_topic_by_id


@dataclass
class StepProgressData:
    """Step progress data for a topic."""

    topic_id: str
    completed_steps: list[int]
    total_steps: int
    next_unlocked_step: int


@dataclass
class StepCompletionResult:
    """Result of completing a step."""

    topic_id: str
    step_order: int
    completed_at: datetime


class StepValidationError(Exception):
    """Raised when step validation fails."""

    pass


class StepAlreadyCompletedError(StepValidationError):
    """Raised when trying to complete an already completed step."""

    pass


class StepNotUnlockedError(StepValidationError):
    """Raised when trying to complete a step that isn't unlocked."""

    def __init__(self, completed_steps: list[int], required_steps: list[int]):
        self.completed_steps = completed_steps
        self.required_steps = required_steps
        super().__init__(
            f"Must complete previous steps first. "
            f"Complete: {sorted(completed_steps)}, "
            f"required: {sorted(required_steps)}"
        )


class StepUnknownTopicError(StepValidationError):
    """Raised when a topic_id doesn't exist in content."""


class StepInvalidStepOrderError(StepValidationError):
    """Raised when step_order is out of range for the topic."""


def _resolve_total_steps(topic_id: str) -> int:
    topic = get_topic_by_id(topic_id)
    if topic is None:
        raise StepUnknownTopicError(f"Unknown topic_id: {topic_id}")
    return len(topic.learning_steps)


def _validate_step_order(topic_id: str, step_order: int) -> int:
    total_steps = _resolve_total_steps(topic_id)
    if step_order < 1 or step_order > total_steps:
        raise StepInvalidStepOrderError(
            f"Invalid step_order {step_order} for {topic_id}. "
            f"Must be between 1 and {total_steps}."
        )
    return total_steps


async def get_topic_step_progress(
    db,
    user_id: str,
    topic_id: str,
    *,
    is_admin: bool = False,
) -> StepProgressData:
    """Get the step progress for a topic.

    Args:
        db: Database session
        user_id: The user's ID
        topic_id: The topic ID (e.g., "phase1-topic5")
    Returns:
        StepProgressData with completed steps and next unlocked step
    """
    total_steps = _resolve_total_steps(topic_id)

    step_repo = StepProgressRepository(db)
    completed_step_orders = await step_repo.get_completed_step_orders(user_id, topic_id)
    completed_steps = sorted(completed_step_orders)

    if is_admin:
        return StepProgressData(
            topic_id=topic_id,
            completed_steps=completed_steps,
            total_steps=total_steps,
            next_unlocked_step=total_steps,
        )

    if not completed_steps:
        next_unlocked = 1
    else:
        max_completed = max(completed_steps)
        if max_completed < total_steps:
            next_unlocked = max_completed + 1
        else:
            next_unlocked = total_steps

    return StepProgressData(
        topic_id=topic_id,
        completed_steps=completed_steps,
        total_steps=total_steps,
        next_unlocked_step=next_unlocked,
    )


@track_operation("step_completion")
async def complete_step(
    db,
    user_id: str,
    topic_id: str,
    step_order: int,
    *,
    is_admin: bool = False,
) -> StepCompletionResult:
    """Mark a learning step as complete.

    Steps must be completed in order - you can only complete step N
    if steps 1 through N-1 are already complete.

    Args:
        db: Database session
        user_id: The user's ID
        topic_id: The topic ID
        step_order: The step number to complete

    Returns:
        StepCompletionResult with completion details

    Raises:
        StepAlreadyCompletedError: If step is already completed
        StepNotUnlockedError: If previous steps are not completed
    """
    add_custom_attribute("step.topic_id", topic_id)
    add_custom_attribute("step.order", step_order)
    _validate_step_order(topic_id, step_order)

    step_repo = StepProgressRepository(db)
    activity_repo = ActivityRepository(db)

    if await step_repo.exists(user_id, topic_id, step_order):
        raise StepAlreadyCompletedError("Step already completed")

    if not is_admin and step_order > 1:
        completed_steps = await step_repo.get_completed_step_orders(user_id, topic_id)

        required_steps = set(range(1, step_order))
        if not required_steps.issubset(completed_steps):
            raise StepNotUnlockedError(
                completed_steps=list(completed_steps),
                required_steps=list(required_steps),
            )

    step_progress = await step_repo.create(
        user_id=user_id,
        topic_id=topic_id,
        step_order=step_order,
    )

    today = datetime.now(UTC).date()
    await activity_repo.log_activity(
        user_id=user_id,
        activity_type=ActivityType.STEP_COMPLETE,
        activity_date=today,
        reference_id=f"{topic_id}:step{step_order}",
    )

    # Invalidate cache so dashboard/progress refreshes immediately
    invalidate_progress_cache(user_id)

    # Extract phase from topic_id (e.g., "phase1-topic4" -> "phase1")
    phase = topic_id.split("-")[0] if "-" in topic_id else "unknown"
    log_metric("steps.completed", 1, {"phase": phase, "topic_id": topic_id})

    return StepCompletionResult(
        topic_id=step_progress.topic_id,
        step_order=step_progress.step_order,
        completed_at=step_progress.completed_at,
    )


async def uncomplete_step(db, user_id: str, topic_id: str, step_order: int) -> int:
    """Mark a learning step as incomplete (uncomplete it).

    Also removes any steps after this one (cascading uncomplete).

    Args:
        db: Database session
        user_id: The user's ID
        topic_id: The topic ID
        step_order: The step number to uncomplete

    Returns:
        Number of steps deleted
    """
    _validate_step_order(topic_id, step_order)

    step_repo = StepProgressRepository(db)
    deleted = await step_repo.delete_from_step(user_id, topic_id, step_order)

    # Invalidate cache so dashboard/progress refreshes immediately
    if deleted > 0:
        invalidate_progress_cache(user_id)

    return deleted
