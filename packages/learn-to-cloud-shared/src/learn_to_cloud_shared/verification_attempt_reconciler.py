"""Pure decision helpers for the stale verification-attempt reconciler.

Kept separate from the Durable/DB glue so the status -> outcome mapping and age
boundary are unit-testable without any Azure client. The reconciler proper
(function_app) queries active attempts, asks Durable for each instance's
status, and applies :func:`reconcile_decision` before a compare-and-set
terminalize.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from learn_to_cloud_shared.models import VerificationAttemptOutcome

# Azure Durable spells the cancelled runtime status ``Canceled`` (one L); the
# DB outcome is ``cancelled`` (two L). Normalizing here keeps every status
# handler in agreement.
AZURE_CANCELED_STATUS = "Canceled"

# Runtime statuses that mean the orchestration can still make progress or was
# intentionally suspended -- never terminalize these.
HEALTHY_STATUSES: frozenset[str] = frozenset(
    {"Running", "Pending", "ContinuedAsNew", "Suspended"}
)

_RECONCILER_SOURCE = "reconciler"


@dataclass(frozen=True, slots=True)
class ReconcileDecision:
    """A terminal outcome the reconciler should compare-and-set for an attempt."""

    outcome: VerificationAttemptOutcome
    error_code: str
    validation_message: str
    terminal_source: str = _RECONCILER_SOURCE


def reconcile_decision(status_name: str | None) -> ReconcileDecision | None:
    """Map a Durable runtime status to a terminal decision, or ``None``.

    ``None`` means "leave the attempt active": either it is genuinely healthy
    (Pending/Running/etc.) or its status is unknown and terminalizing would be
    unsafe. A missing status (``status_name is None``) is a confirmed
    not-started/abandoned instance and terminalizes as ``server_error``.
    """
    if status_name is None:
        return ReconcileDecision(
            outcome=VerificationAttemptOutcome.SERVER_ERROR,
            error_code="server_error",
            validation_message="Verification never started and was reconciled.",
        )
    if status_name in HEALTHY_STATUSES:
        return None
    if status_name == "Completed":
        return ReconcileDecision(
            outcome=VerificationAttemptOutcome.SERVER_ERROR,
            error_code="server_error",
            validation_message=(
                "Verification completed without recording a result and was reconciled."
            ),
        )
    if status_name in {"Terminated", AZURE_CANCELED_STATUS}:
        return ReconcileDecision(
            outcome=VerificationAttemptOutcome.CANCELLED,
            error_code="cancelled",
            validation_message="Verification was cancelled.",
        )
    if status_name == "Failed":
        return ReconcileDecision(
            outcome=VerificationAttemptOutcome.SERVER_ERROR,
            error_code="server_error",
            validation_message="Verification failed and was reconciled.",
        )
    # Any status this code does not recognize is left untouched -- being
    # conservative here means an unfamiliar-but-healthy state is never
    # mistakenly terminalized.
    return None


def stale_cutoff(now: datetime, min_age_minutes: int) -> datetime:
    """Return the newest ``created_at`` an attempt may have and still be stale."""
    return now - timedelta(minutes=min_age_minutes)
