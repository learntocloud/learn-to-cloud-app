"""Step progress service for learning step management.

After the Phase E follow-up that dropped legacy id columns, the unit of
identity for steps is ``step.uuid``. The HTMX endpoints take a step
UUID directly; the topic context is recovered (when needed for
rendering) by walking the loaded curriculum tree.
"""

from typing import TYPE_CHECKING
from uuid import UUID

from learn_to_cloud_shared.content_service import get_all_phases
from learn_to_cloud_shared.models import utcnow
from learn_to_cloud_shared.repositories import StepProgressRepository
from learn_to_cloud_shared.schemas import LearningStep, StepCompletionResult
from opentelemetry import trace
from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from learn_to_cloud_shared.schemas import Topic


class StepValidationError(Exception):
    """Raised when step validation fails."""


class StepNotFoundError(StepValidationError):
    """Raised when a step_uuid does not exist in the loaded curriculum."""

    def __init__(self, step_uuid: UUID):
        self.step_uuid = step_uuid
        super().__init__(f"Unknown step_uuid: {step_uuid}")


async def _find_step(db: AsyncSession, step_uuid: UUID) -> tuple["Topic", LearningStep]:
    """Resolve a step UUID to its parent topic + step model.

    Walks the in-memory curriculum tree (small N). Soft-deleted steps
    are excluded because ``get_all_phases`` only returns active rows;
    raising :class:`StepNotFoundError` keeps the surface uniform with
    the verification request paths.
    """
    phases = await get_all_phases(db)
    for phase in phases:
        for topic in phase.topics:
            for step in topic.learning_steps:
                if step.uuid == step_uuid:
                    return topic, step
    raise StepNotFoundError(step_uuid)


async def get_valid_completed_steps(
    db: AsyncSession,
    user_id: int,
    topic: "Topic",
) -> set[UUID]:
    """Get completed step UUIDs filtered to steps that exist in this topic."""
    step_repo = StepProgressRepository(db)
    return await step_repo.get_completed_step_uuids(
        user_id, (step.uuid for step in topic.learning_steps)
    )


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
    topic, step = await _find_step(db, step_uuid)

    step_repo = StepProgressRepository(db)
    step_progress = await step_repo.create_if_not_exists(
        user_id=user_id,
        step_uuid=step.uuid,
    )

    span = trace.get_current_span()
    span.set_attribute("step.uuid", str(step.uuid))
    span.set_attribute("step.slug", step.slug)
    span.set_attribute("topic.slug", topic.slug)
    span.set_attribute("step.order", step.order)

    completed = await get_valid_completed_steps(db, user_id, topic)

    if step_progress is None:
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
            completed_at=step_progress.completed_at,
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
    topic, step = await _find_step(db, step_uuid)

    step_repo = StepProgressRepository(db)
    deleted = await step_repo.delete_step(user_id, step.uuid)

    span = trace.get_current_span()
    span.set_attribute("step.uuid", str(step.uuid))
    span.set_attribute("step.slug", step.slug)
    span.set_attribute("topic.slug", topic.slug)
    span.set_attribute("step.order", step.order)
    span.set_attribute("step.action", "uncompleted")

    completed = await get_valid_completed_steps(db, user_id, topic)

    return deleted, topic, step, completed
