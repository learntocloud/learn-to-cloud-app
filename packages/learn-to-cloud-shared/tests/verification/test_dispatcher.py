"""Tests for the sync/async dispatch helper in the verification dispatcher."""

import pytest

from learn_to_cloud_shared.models import SubmissionType
from learn_to_cloud_shared.verification.dispatcher import (
    SYNC_VERIFIABLE_SUBMISSION_TYPES,
    is_sync_verifiable,
)

_EXPECTED_SYNC = {
    SubmissionType.GITHUB_PROFILE,
    SubmissionType.PROFILE_README,
    SubmissionType.REPO_FORK,
    SubmissionType.CTF_TOKEN,
    SubmissionType.NETWORKING_TOKEN,
}


def test_sync_verifiable_set_is_exactly_the_phase_0_to_2_types():
    """Guard rail: any new sync type must be added intentionally.

    Keeping this assertion concrete protects against silently routing a
    new phase 3+ verification through the in-request path.
    """
    assert SYNC_VERIFIABLE_SUBMISSION_TYPES == _EXPECTED_SYNC


@pytest.mark.parametrize(
    "submission_type", sorted(_EXPECTED_SYNC, key=lambda t: t.value)
)
def test_is_sync_verifiable_true_for_phase_0_to_2_types(submission_type):
    assert is_sync_verifiable(submission_type) is True


@pytest.mark.parametrize(
    "submission_type",
    sorted(set(SubmissionType) - _EXPECTED_SYNC, key=lambda t: t.value),
)
def test_is_sync_verifiable_false_for_async_types(submission_type):
    assert is_sync_verifiable(submission_type) is False
