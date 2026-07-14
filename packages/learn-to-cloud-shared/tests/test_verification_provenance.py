"""Unit tests for verification-attempt provenance helpers."""

from __future__ import annotations

from uuid import UUID

import pytest

from learn_to_cloud_shared.models import VerificationAttemptOutcome
from learn_to_cloud_shared.verification_provenance import (
    ORPHAN_SUBMISSION_ATTEMPT_NAMESPACE,
    attempt_id_for_orphan_submission,
    derive_outcome,
)


class TestDeriveOutcome:
    def test_validated_is_succeeded(self):
        outcome = derive_outcome(is_validated=True, verification_completed=True)
        assert outcome is VerificationAttemptOutcome.SUCCEEDED

    def test_completed_not_validated_is_failed(self):
        outcome = derive_outcome(is_validated=False, verification_completed=True)
        assert outcome is VerificationAttemptOutcome.FAILED

    def test_not_completed_is_server_error(self):
        outcome = derive_outcome(is_validated=False, verification_completed=False)
        assert outcome is VerificationAttemptOutcome.SERVER_ERROR

    def test_validated_wins_over_incomplete(self):
        # is_validated should dominate even if verification_completed is False.
        outcome = derive_outcome(is_validated=True, verification_completed=False)
        assert outcome is VerificationAttemptOutcome.SUCCEEDED


class TestOrphanAttemptId:
    def test_is_deterministic(self):
        assert attempt_id_for_orphan_submission(42) == (
            attempt_id_for_orphan_submission(42)
        )

    def test_distinct_ids_for_distinct_submissions(self):
        assert attempt_id_for_orphan_submission(1) != (
            attempt_id_for_orphan_submission(2)
        )

    def test_is_uuid5_of_documented_namespace(self):
        from uuid import uuid5

        expected = uuid5(ORPHAN_SUBMISSION_ATTEMPT_NAMESPACE, "submission:7")
        assert attempt_id_for_orphan_submission(7) == expected

    def test_namespace_is_pinned(self):
        # This value anchors every orphan-submission attempt id in history
        # and must never change.
        assert ORPHAN_SUBMISSION_ATTEMPT_NAMESPACE == UUID(
            "b27a6ab3-3d05-4918-8de2-0ef02aac06a9"
        )


def test_outcome_enum_values():
    assert {o.value for o in VerificationAttemptOutcome} == {
        "succeeded",
        "failed",
        "server_error",
        "cancelled",
    }


def test_snapshot_source_enum_values():
    from learn_to_cloud_shared.models import VerificationSnapshotSource

    assert {s.value for s in VerificationSnapshotSource} == {
        "submitted",
        "reconstructed",
    }


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
