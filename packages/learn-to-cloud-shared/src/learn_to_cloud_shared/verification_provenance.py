"""Historical helpers imported by Alembic revision 0049."""

from __future__ import annotations

from uuid import UUID, uuid5

from learn_to_cloud_shared.models import VerificationAttemptOutcome

ORPHAN_SUBMISSION_ATTEMPT_NAMESPACE = UUID("b27a6ab3-3d05-4918-8de2-0ef02aac06a9")

_ORPHAN_NAME_PREFIX = "submission:"


def attempt_id_for_orphan_submission(submission_id: int) -> UUID:
    """Return the stable attempt UUID used by the historical backfill."""
    return uuid5(
        ORPHAN_SUBMISSION_ATTEMPT_NAMESPACE,
        f"{_ORPHAN_NAME_PREFIX}{submission_id}",
    )


def derive_outcome(
    *,
    is_validated: bool,
    verification_completed: bool,
) -> VerificationAttemptOutcome:
    """Map historical submission flags to an attempt outcome."""
    if is_validated:
        return VerificationAttemptOutcome.SUCCEEDED
    if verification_completed:
        return VerificationAttemptOutcome.FAILED
    return VerificationAttemptOutcome.SERVER_ERROR
