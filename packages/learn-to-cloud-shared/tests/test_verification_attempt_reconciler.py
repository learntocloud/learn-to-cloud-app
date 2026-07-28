"""Unit tests for the stale verification-attempt reconciler decisions."""

from __future__ import annotations

from datetime import UTC, datetime

from learn_to_cloud_shared.models import VerificationAttemptOutcome
from learn_to_cloud_shared.verification_attempt_reconciler import (
    reconcile_decision,
    stale_cutoff,
)


def test_missing_status_terminalizes_as_server_error() -> None:
    decision = reconcile_decision(None)
    assert decision is not None
    assert decision.outcome is VerificationAttemptOutcome.SERVER_ERROR
    assert decision.error_code == "server_error"


def test_failed_maps_to_server_error() -> None:
    decision = reconcile_decision("Failed")
    assert decision is not None
    assert decision.outcome is VerificationAttemptOutcome.SERVER_ERROR


def test_terminated_maps_to_cancelled() -> None:
    decision = reconcile_decision("Terminated")
    assert decision is not None
    assert decision.outcome is VerificationAttemptOutcome.CANCELLED


def test_azure_canceled_spelling_maps_to_cancelled() -> None:
    decision = reconcile_decision("Canceled")
    assert decision is not None
    assert decision.outcome is VerificationAttemptOutcome.CANCELLED
    assert decision.error_code == "cancelled"


def test_healthy_statuses_are_left_untouched() -> None:
    for status in ("Running", "Pending", "ContinuedAsNew", "Suspended"):
        assert reconcile_decision(status) is None


def test_completed_without_persisted_outcome_maps_to_server_error() -> None:
    decision = reconcile_decision("Completed")
    assert decision is not None
    assert decision.outcome is VerificationAttemptOutcome.SERVER_ERROR


def test_unknown_status_is_left_untouched() -> None:
    assert reconcile_decision("SomethingNew") is None


def test_stale_cutoff_subtracts_minutes() -> None:
    now = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    cutoff = stale_cutoff(now, 30)
    assert cutoff == datetime(2026, 1, 1, 11, 30, tzinfo=UTC)
