"""Step progress service for learning step management."""

import logging
from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession

from models import utcnow
from repositories import StepProgressRepository
from schemas import StepCompletionResult
from services.content_service import get_topic_by_id

if TYPE_CHECKING:
    from schemas import Topic

logger = logging.getLogger(__name__)


class StepValidationError(Exception):
    """Raised when step validation fails."""


class StepUnknownTopicError(StepValidationError):
    """Raised when a topic_id doesn't exist in content."""

    def __init__(self, topic_id: str):
        self.topic_id = topic_id
        super().__init__(f"Unknown topic_id: {topic_id}")


class StepInvalidStepIdError(StepValidationError):
    """Raised when a step_id does not exist in the topic."""

    def __init__(self, topic_id: str, step_id: str):
        self.topic_id = topic_id
        self.step_id = step_id
        super().__init__(f"Invalid step_id '{step_id}' for {topic_id}")


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


async def get_valid_completed_steps(
    db: AsyncSession,
    user_id: int,
    topic: "Topic",
) -> set[str]:
    """Get completed step IDs filtered to only steps that exist in content.

    Prevents stale step IDs (from removed/renamed content) from inflating
    progress counts.
    """
    step_repo = StepProgressRepository(db)
    completed = await step_repo.get_completed_step_ids(user_id, topic.id)
    valid_ids = {step.id for step in topic.learning_steps}
    return completed & valid_ids


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

    step_progress = await step_repo.create_if_not_exists(
        user_id=user_id,
        topic_id=topic_id,
        step_id=resolved_step_id,
        step_order=step_order,
        phase_id=phase_id,
    )
    # Step already completed — idempotent no-op
    if step_progress is None:
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

    logger.info(
        "step.completed",
        extra={
            "user_id": user_id,
            "topic_id": topic_id,
            "step_id": resolved_step_id,
            "step_order": step_order,
        },
    )

    completed_steps = await step_repo.get_completed_step_ids(user_id, topic_id)

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
    """Mark a single learning step as incomplete.

    Only removes the specified step — does not cascade to other steps.

    Args:
        db: Database session
        user_id: The user's ID
        topic_id: The topic ID
        step_id: The stable step identifier to uncomplete

    Returns:
        Tuple of (number of steps deleted, updated completed step orders)

    Raises:
        StepUnknownTopicError: If topic_id doesn't exist in content
        StepInvalidStepIdError: If step_id doesn't exist in the topic
    """
    resolved_step_id, step_order, _ = _resolve_step(topic_id, step_id)

    step_repo = StepProgressRepository(db)
    deleted = await step_repo.delete_step(user_id, topic_id, resolved_step_id)

    if deleted > 0:
        logger.info(
            "step.uncompleted",
            extra={
                "user_id": user_id,
                "topic_id": topic_id,
                "step_id": resolved_step_id,
                "step_order": step_order,
            },
        )

    completed_steps = await step_repo.get_completed_step_ids(user_id, topic_id)

    return deleted, completed_steps
