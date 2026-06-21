"""Tests for the registry-driven dispatch in the verification dispatcher.

Each submission type's behavior (execution mode, username requirement, and
whether it is repo-backed) is declared once in ``_VALIDATOR_REGISTRY``. These
tests pin that registry so a new or changed type can't silently alter routing.
"""

import pytest

from learn_to_cloud_shared.models import ExecutionMode, SubmissionType
from learn_to_cloud_shared.verification.dispatcher import (
    _VALIDATOR_REGISTRY,
    descriptor_for,
    execution_mode_for,
    is_inline,
    is_repo_backed,
)

# The submission types that run inside the FastAPI request (phases 0-2).
_EXPECTED_INLINE = {
    SubmissionType.GITHUB_PROFILE,
    SubmissionType.PROFILE_README,
    SubmissionType.REPO_FORK,
    SubmissionType.CTF_TOKEN,
    SubmissionType.NETWORKING_TOKEN,
}

# The submission types that go through Durable Functions (phases 3-6).
_EXPECTED_BACKGROUND = {
    SubmissionType.JOURNAL_API_VERIFIER,
    SubmissionType.DEVOPS_ANALYSIS,
    SubmissionType.DEPLOYED_API,
    SubmissionType.SECURITY_SCANNING,
}

# Server-derived GitHub repo URL types (owner/repo parsed from the value).
_EXPECTED_REPO_BACKED = {
    SubmissionType.JOURNAL_API_VERIFIER,
    SubmissionType.DEVOPS_ANALYSIS,
    SubmissionType.SECURITY_SCANNING,
}

# The only type that does not require a GitHub username.
_EXPECTED_NO_USERNAME = {SubmissionType.DEPLOYED_API}

# Every submission type now has an active validator descriptor.
_ACTIVE_TYPES = {member.value for member in SubmissionType}


def test_inline_set_is_exactly_the_phase_0_to_2_types():
    """Guard rail: any new inline type must be added intentionally.

    Keeping this concrete protects against silently routing a new phase 3+
    verification through the in-request path.
    """
    inline = {t for t in _VALIDATOR_REGISTRY if is_inline(t)}
    assert inline == _EXPECTED_INLINE


@pytest.mark.parametrize(
    "submission_type", sorted(_EXPECTED_INLINE, key=lambda t: t.value)
)
def test_is_inline_true_for_inline_types(submission_type):
    assert is_inline(submission_type) is True
    assert execution_mode_for(submission_type) is ExecutionMode.INLINE


@pytest.mark.parametrize(
    "submission_type", sorted(_EXPECTED_BACKGROUND, key=lambda t: t.value)
)
def test_is_inline_false_for_background_types(submission_type):
    assert is_inline(submission_type) is False
    assert execution_mode_for(submission_type) is ExecutionMode.BACKGROUND


@pytest.mark.parametrize(
    "submission_type", sorted(_EXPECTED_REPO_BACKED, key=lambda t: t.value)
)
def test_repo_backed_true_for_repo_url_types(submission_type):
    assert is_repo_backed(submission_type) is True


@pytest.mark.parametrize(
    "submission_type",
    sorted(_EXPECTED_INLINE | _EXPECTED_NO_USERNAME, key=lambda t: t.value),
)
def test_repo_backed_false_for_non_repo_types(submission_type):
    assert is_repo_backed(submission_type) is False


@pytest.mark.parametrize(
    "submission_type",
    sorted(
        set(SubmissionType) - _EXPECTED_NO_USERNAME,
        key=lambda t: t.value,
    ),
)
def test_requires_username_true_except_deployed_api(submission_type):
    descriptor = descriptor_for(submission_type)
    assert descriptor is not None
    assert descriptor.requires_username is True


def test_deployed_api_does_not_require_username():
    descriptor = descriptor_for(SubmissionType.DEPLOYED_API)
    assert descriptor is not None
    assert descriptor.requires_username is False


def test_registry_covers_every_active_submission_type_exactly_once():
    """Completeness: each active type has exactly one descriptor, no extras.

    ``_ACTIVE_TYPES`` is derived from the full SubmissionType enum, so adding a
    real type without registering it fails here.
    """
    registry_values = {t.value for t in _VALIDATOR_REGISTRY}
    assert registry_values == _ACTIVE_TYPES
