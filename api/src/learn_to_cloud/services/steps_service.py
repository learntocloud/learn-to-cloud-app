"""Step progress service for learning step management."""

from typing import TYPE_CHECKING
from uuid import UUID

from learn_to_cloud_shared.content_service import get_topic_by_id
from learn_to_cloud_shared.models import utcnow
from learn_to_cloud_shared.repositories import StepProgressRepository
from learn_to_cloud_shared.schemas import StepCompletionResult
from opentelemetry import trace
from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from learn_to_cloud_shared.schemas import Topic


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


async def _resolve_step(
    db: AsyncSession, topic_id: str, step_id: str
) -> tuple[str, int, int, UUID]:
    """Resolve and validate a step by stable step id.

    Returns:
        Tuple of (resolved_step_id, step_order, total_steps, step_uuid).
    """
    topic = await get_topic_by_id(db, topic_id)
    if topic is None:
        raise StepUnknownTopicError(topic_id)

    total_steps = len(topic.learning_steps)
    for step in topic.learning_steps:
        if step.id == step_id:
            return step.id, step.order, total_steps, step.uuid

    raise StepInvalidStepIdError(topic_id, step_id)


def parse_phase_id_from_topic_id(topic_id: str) -> int | None:
    """Extract phase ID from a topic_id string (e.g., 'phase1-topic5' -> 1).

    Used by the HTMX templates to render phase-aware navigation. The
    DB no longer carries ``step_progress.phase_id`` (Phase D.1c of
    #465) but the URL contract still uses phase ids, so callers parse
    them from the topic id string.
    """
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

    The repo speaks UUIDs; we translate back to the human-readable step
    IDs the rest of the app and templates expect. Soft-deleted steps
    drop out automatically because ``topic.learning_steps`` only
    contains active steps.
    """
    step_repo = StepProgressRepository(db)
    completed_uuids = await step_repo.get_completed_step_uuids(
        user_id, (step.uuid for step in topic.learning_steps)
    )
    return {step.id for step in topic.learning_steps if step.uuid in completed_uuids}


async def complete_step(
    db: AsyncSession,
    user_id: int,
    topic_id: str,
    step_id: str,
) -> tuple[StepCompletionResult, set[str]]:
    """Mark a learning step as complete.

    Steps can be completed in any order. Idempotent -- completing an
    already-completed step is a no-op that returns the current state
    without error.
    """
    resolved_step_id, step_order, _, step_uuid = await _resolve_step(
        db, topic_id, step_id
    )

    step_repo = StepProgressRepository(db)
    step_progress = await step_repo.create_if_not_exists(
        user_id=user_id,
        step_uuid=step_uuid,
    )

    span = trace.get_current_span()
    span.set_attribute("step.topic_id", topic_id)
    span.set_attribute("step.step_id", resolved_step_id)
    span.set_attribute("step.order", step_order)

    topic = await get_topic_by_id(db, topic_id)
    completed_steps: set[str] = set()
    if topic is not None:
        completed_steps = await get_valid_completed_steps(db, user_id, topic)

    if step_progress is None:
        span.set_attribute("step.action", "already_completed")
        return StepCompletionResult(
            topic_id=topic_id,
            step_id=resolved_step_id,
            completed_at=utcnow(),
        ), completed_steps

    span.set_attribute("step.action", "completed")

    return StepCompletionResult(
        topic_id=topic_id,
        step_id=resolved_step_id,
        completed_at=step_progress.completed_at,
    ), completed_steps


async def uncomplete_step(
    db: AsyncSession,
    user_id: int,
    topic_id: str,
    step_id: str,
) -> tuple[int, set[str]]:
    """Mark a single learning step as incomplete.

    Only removes the specified step -- does not cascade to other steps.

    Raises:
        StepUnknownTopicError: If topic_id doesn't exist in content
        StepInvalidStepIdError: If step_id doesn't exist in the topic
    """
    resolved_step_id, step_order, _, step_uuid = await _resolve_step(
        db, topic_id, step_id
    )

    step_repo = StepProgressRepository(db)
    deleted = await step_repo.delete_step(user_id, step_uuid)

    span = trace.get_current_span()
    span.set_attribute("step.topic_id", topic_id)
    span.set_attribute("step.step_id", resolved_step_id)
    span.set_attribute("step.order", step_order)
    span.set_attribute("step.action", "uncompleted")

    topic = await get_topic_by_id(db, topic_id)
    completed_steps: set[str] = set()
    if topic is not None:
        completed_steps = await get_valid_completed_steps(db, user_id, topic)

    return deleted, completed_steps
