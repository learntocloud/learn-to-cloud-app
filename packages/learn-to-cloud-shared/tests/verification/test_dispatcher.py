"""Tests for the registry-driven dispatch in the verification dispatcher.

Each submission type's behavior (username requirement and whether it is
repo-backed) is declared once in ``_VALIDATOR_REGISTRY``. These tests pin that
registry so a new or changed type can't silently alter routing.
"""

import pytest

from learn_to_cloud_shared.models import SubmissionType
from learn_to_cloud_shared.verification.dispatcher import (
    _VALIDATOR_REGISTRY,
    descriptor_for,
    is_repo_backed,
)

# Server-derived GitHub repo URL types (owner/repo parsed from the value).
_EXPECTED_REPO_BACKED = {
    SubmissionType.JOURNAL_API_VERIFIER,
    SubmissionType.DEVOPS_ANALYSIS,
    SubmissionType.SECURITY_SCANNING,
}

# The types that do not require a GitHub username.
_EXPECTED_NO_USERNAME = {
    SubmissionType.DEPLOYED_API,
    SubmissionType.CAREER_REFLECTION,
}

# Every submission type now has an active validator descriptor.
_ACTIVE_TYPES = {member.value for member in SubmissionType}


@pytest.mark.parametrize(
    "submission_type", sorted(_EXPECTED_REPO_BACKED, key=lambda t: t.value)
)
def test_repo_backed_true_for_repo_url_types(submission_type):
    assert is_repo_backed(submission_type) is True


@pytest.mark.parametrize(
    "submission_type",
    sorted(
        (set(SubmissionType) - _EXPECTED_REPO_BACKED),
        key=lambda t: t.value,
    ),
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


def test_deployment_architecture_is_repo_derived_needs_username():
    descriptor = descriptor_for(SubmissionType.DEPLOYMENT_ARCHITECTURE)
    assert descriptor is not None
    assert descriptor.requires_username is True
    # The submitted value is free text, not a repo URL, so it is not
    # repo-backed even though the validator derives a repo from required_repo.
    assert descriptor.repo_backed is False
    assert is_repo_backed(SubmissionType.DEPLOYMENT_ARCHITECTURE) is False


def test_registry_covers_every_active_submission_type_exactly_once():
    """Completeness: each active type has exactly one descriptor, no extras.

    ``_ACTIVE_TYPES`` is derived from the full SubmissionType enum, so adding a
    real type without registering it fails here.
    """
    registry_values = {t.value for t in _VALIDATOR_REGISTRY}
    assert registry_values == _ACTIVE_TYPES
