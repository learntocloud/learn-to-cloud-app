"""Authoritative-with-narrow-legacy-fallback learner-state reads (PR6).

Shared by sequential phase gating (``requirements.py``), submission
preconditions, and per-user/per-phase progress computation -- anywhere the
app needs "has this user completed these steps / succeeded at these
requirements" against the authoritative ``learner_step_completions`` /
``verification_attempts`` tables.

The legacy fallback exists only for records not yet reconciled/mirrored
during the PR5/PR6 mixed-revision window: an authoritative row always wins
regardless of legacy state, and legacy data is only consulted to fill a
genuine gap (a step/requirement with nothing authoritative recorded at all).
Fallback usage is logged (``progress.legacy_fallback_used``) so PR8 can
detect when the fallback path is no longer exercised and remove it.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from learn_to_cloud_shared.repositories.learner_step_completion_repository import (
    LearnerStepCompletionRepository,
)
from learn_to_cloud_shared.repositories.progress_repository import (
    StepProgressRepository,
)
from learn_to_cloud_shared.repositories.submission_repository import (
    SubmissionRepository,
)
from learn_to_cloud_shared.repositories.verification_attempt_repository import (
    VerificationAttemptRepository,
)

logger = logging.getLogger(__name__)


def _log_legacy_fallback_used(*, user_id: int, kind: str, count: int) -> None:
    logger.warning(
        "progress.legacy_fallback_used",
        extra={"user_id": user_id, "kind": kind, "count": count},
    )


async def resolve_completed_step_uuids(
    db: AsyncSession,
    user_id: int,
    candidate_step_uuids: Iterable[UUID],
) -> tuple[set[UUID], set[UUID]]:
    """Resolve completed steps, trusting ``learner_step_completions`` first.

    Any step UUID recorded there is authoritative and wins outright. Only a
    UUID present in the legacy ``step_progress`` table but absent from the
    authoritative one (a mirroring gap) is folded in as a fallback.

    Returns ``(completed_uuids, legacy_fallback_only_uuids)`` -- the second
    set is the subset of the first that came *only* from the legacy table.
    """
    uuids = list(candidate_step_uuids)
    if not uuids:
        return set(), set()

    authoritative = await LearnerStepCompletionRepository(db).get_completed_step_uuids(
        user_id, uuids
    )
    legacy = await StepProgressRepository(db).get_completed_step_uuids(user_id, uuids)
    fallback_only = legacy - authoritative
    if fallback_only:
        _log_legacy_fallback_used(
            user_id=user_id, kind="step", count=len(fallback_only)
        )
    return authoritative | fallback_only, fallback_only


async def resolve_succeeded_requirement_uuids(
    db: AsyncSession,
    user_id: int,
    candidate_requirement_uuids: Iterable[UUID],
) -> tuple[set[UUID], set[UUID]]:
    """Resolve succeeded requirements, trusting ``verification_attempts`` first.

    A requirement with *any* attempt row (active or terminal) is fully
    trusted -- only ``outcome == 'succeeded'`` counts, regardless of legacy
    state. Legacy ``submissions.is_validated`` is only consulted for a
    requirement with zero attempt rows at all, the mixed-revision gap this
    fallback exists for.

    Returns ``(succeeded_uuids, legacy_fallback_only_uuids)``.
    """
    uuids = set(candidate_requirement_uuids)
    if not uuids:
        return set(), set()

    attempt_repo = VerificationAttemptRepository(db)
    succeeded = await attempt_repo.get_succeeded_requirement_uuids(user_id)
    succeeded &= uuids

    attempted = await attempt_repo.get_requirement_uuids_with_any_attempt(
        user_id, uuids
    )
    unattempted = uuids - attempted
    if not unattempted:
        return succeeded, set()

    legacy_validated = await SubmissionRepository(db).get_validated_requirement_uuids(
        user_id
    )
    fallback_only = legacy_validated & unattempted
    if fallback_only:
        _log_legacy_fallback_used(
            user_id=user_id, kind="requirement", count=len(fallback_only)
        )
    return succeeded | fallback_only, fallback_only


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
    succeeded, _ = await resolve_succeeded_requirement_uuids(db, user_id, uuids)
    return len(succeeded) >= len(uuids)
