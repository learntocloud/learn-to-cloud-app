"""Deterministic provenance helpers for the verification-attempt backfill.

Shared by the expand migration, the reconciliation report, and their
tests so the id derivation and outcome mapping stay in exact agreement.
"""

from __future__ import annotations

from uuid import UUID, uuid5

from learn_to_cloud_shared.models import VerificationAttemptOutcome

# Fixed, documented namespace for deriving a verification-attempt id from a
# legacy submission that never had a verification_jobs row. UUIDv5 keeps the
# mapping deterministic so the backfill is idempotent and re-runnable. Do not
# change this value: it anchors every orphan-submission attempt id in history.
ORPHAN_SUBMISSION_ATTEMPT_NAMESPACE = UUID("b27a6ab3-3d05-4918-8de2-0ef02aac06a9")

_ORPHAN_NAME_PREFIX = "submission:"


def attempt_id_for_orphan_submission(submission_id: int) -> UUID:
    """Return the deterministic attempt id for a job-less submission."""
    return uuid5(
        ORPHAN_SUBMISSION_ATTEMPT_NAMESPACE,
        f"{_ORPHAN_NAME_PREFIX}{submission_id}",
    )


def derive_outcome(
    *,
    is_validated: bool,
    verification_completed: bool,
) -> VerificationAttemptOutcome:
    """Map a legacy submission's flags to a terminal attempt outcome.

    ``is_validated`` wins (succeeded); a completed-but-not-validated run is a
    genuine ``failed`` verification; anything else never finished verifying
    and is recorded as ``server_error``.
    """
    if is_validated:
        return VerificationAttemptOutcome.SUCCEEDED
    if verification_completed:
        return VerificationAttemptOutcome.FAILED
    return VerificationAttemptOutcome.SERVER_ERROR
