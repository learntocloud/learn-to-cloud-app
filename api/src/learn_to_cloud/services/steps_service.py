"""Learning-step completion service."""

import logging
from typing import TYPE_CHECKING
from uuid import UUID

from learn_to_cloud_shared.content_service import get_topic_containing_step
from learn_to_cloud_shared.models import utcnow
from learn_to_cloud_shared.progress_reads import resolve_completed_step_uuids
from learn_to_cloud_shared.repositories import (
    LearnerStepCompletionRepository,
    StepProgressRepository,
)
from learn_to_cloud_shared.schemas import LearningStep, StepCompletionResult
from opentelemetry import trace
from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from learn_to_cloud_shared.schemas import Topic

logger = logging.getLogger(__name__)


class StepValidationError(Exception):
    """Raised when step validation fails."""


class StepNotFoundError(StepValidationError):
    """Raised when a step_uuid does not exist in the loaded curriculum."""

    def __init__(self, step_uuid: UUID):
        self.step_uuid = step_uuid
        super().__init__(f"Unknown step_uuid: {step_uuid}")


def _find_step(step_uuid: UUID) -> tuple["Topic", LearningStep]:
    """Resolve a step UUID to its parent topic + step model.

    In-memory catalog lookup, not the entire curriculum tree walked per
    call. Raises :class:`StepNotFoundError` for unknown UUIDs, keeping
    the surface uniform with the verification request paths.
    """
    result = get_topic_containing_step(step_uuid)
    if result is None:
        raise StepNotFoundError(step_uuid)
    return result


async def get_valid_completed_steps(
    db: AsyncSession,
    user_id: int,
    topic: "Topic",
) -> set[UUID]:
    """Get completed step UUIDs filtered to steps that exist in this topic."""
    completed, _ = await resolve_completed_step_uuids(
        db, user_id, (step.uuid for step in topic.learning_steps)
    )
    return completed


async def complete_step(
    db: AsyncSession,
    user_id: int,
    step_uuid: UUID,
) -> tuple[StepCompletionResult, "Topic", set[UUID]]:
    """Mark a learning step as complete.

    Idempotent -- completing an already-completed step is a no-op that
    returns the current state without error.

    Returns the (result, parent topic, set of completed step UUIDs in
    that topic) tuple so the HTMX caller can re-render the step partial
    and the topic progress bar without re-loading the curriculum.
    """
    topic, step = _find_step(step_uuid)

    completed_at = utcnow()
    completion = await LearnerStepCompletionRepository(db).create_if_not_exists(
        user_id=user_id,
        step_uuid=step.uuid,
        completed_at=completed_at,
    )

    span = trace.get_current_span()
    span.set_attribute("step.uuid", str(step.uuid))
    span.set_attribute("step.slug", step.slug)
    span.set_attribute("topic.slug", topic.slug)
    span.set_attribute("step.order", step.order)

    completed = await get_valid_completed_steps(db, user_id, topic)

    if completion is None:
        span.set_attribute("step.action", "already_completed")
        return (
            StepCompletionResult(
                topic_slug=topic.slug,
                step_slug=step.slug,
                completed_at=utcnow(),
            ),
            topic,
            completed,
        )

    span.set_attribute("step.action", "completed")

    return (
        StepCompletionResult(
            topic_slug=topic.slug,
            step_slug=step.slug,
            completed_at=completion.completed_at,
        ),
        topic,
        completed,
    )


async def uncomplete_step(
    db: AsyncSession,
    user_id: int,
    step_uuid: UUID,
) -> tuple[int, "Topic", LearningStep, set[UUID]]:
    """Mark a single learning step as incomplete.

    Only removes the specified step -- does not cascade.

    Raises:
        StepNotFoundError: If step_uuid doesn't exist in active content.
    """
    topic, step = _find_step(step_uuid)

    authoritative_deleted = await LearnerStepCompletionRepository(db).delete(
        user_id=user_id, step_uuid=step.uuid
    )
    # Until the legacy fallback is removed, an old row would otherwise make
    # this step appear complete again. This delete-through creates no new
    # legacy state and is removed with the fallback in the contract layer.
    legacy_deleted = await StepProgressRepository(db).delete_step(user_id, step.uuid)
    if legacy_deleted:
        logger.warning(
            "step.legacy_delete_through_used",
            extra={"user_id": user_id, "step_uuid": str(step.uuid)},
        )
    deleted = max(authoritative_deleted, legacy_deleted)

    span = trace.get_current_span()
    span.set_attribute("step.uuid", str(step.uuid))
    span.set_attribute("step.slug", step.slug)
    span.set_attribute("topic.slug", topic.slug)
    span.set_attribute("step.order", step.order)
    span.set_attribute("step.action", "uncompleted")

    completed = await get_valid_completed_steps(db, user_id, topic)

    return deleted, topic, step, completed
