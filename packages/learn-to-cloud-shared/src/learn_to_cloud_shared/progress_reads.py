"""Authoritative learner progress reads."""

from __future__ import annotations

from collections.abc import Iterable
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from learn_to_cloud_shared.repositories.learner_step_completion_repository import (
    LearnerStepCompletionRepository,
)
from learn_to_cloud_shared.repositories.verification_attempt_repository import (
    VerificationAttemptRepository,
)


async def resolve_completed_step_uuids(
    db: AsyncSession,
    user_id: int,
    candidate_step_uuids: Iterable[UUID],
) -> set[UUID]:
    """Return completed UUIDs among the candidate catalog steps."""
    uuids = list(candidate_step_uuids)
    if not uuids:
        return set()
    return await LearnerStepCompletionRepository(db).get_completed_step_uuids(
        user_id, uuids
    )


async def resolve_succeeded_requirement_uuids(
    db: AsyncSession,
    user_id: int,
    candidate_requirement_uuids: Iterable[UUID],
) -> set[UUID]:
    """Return succeeded UUIDs among the candidate catalog requirements."""
    uuids = set(candidate_requirement_uuids)
    if not uuids:
        return set()

    succeeded = await VerificationAttemptRepository(db).get_succeeded_requirement_uuids(
        user_id
    )
    succeeded &= uuids
    return succeeded


async def are_all_requirements_succeeded(
    db: AsyncSession,
    user_id: int,
    requirement_uuids: Iterable[UUID],
) -> bool:
    """Check if the user has succeeded at ALL of the given requirements.

    Used for sequential phase gating and the "already validated" submission
    precondition check.
    """
    uuids = list(requirement_uuids)
    if not uuids:
        return True
    succeeded = await resolve_succeeded_requirement_uuids(db, user_id, uuids)
    return len(succeeded) >= len(uuids)
