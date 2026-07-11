"""Tests for the registry-driven dispatch in the verification dispatcher.

Each submission type's username requirement is declared once in
``_VALIDATOR_REGISTRY``. These tests pin that registry so a new or changed type
can't silently alter routing.
"""

import pytest

from learn_to_cloud_shared.models import SubmissionType
from learn_to_cloud_shared.verification.dispatcher import (
    _VALIDATOR_REGISTRY,
    descriptor_for,
)

# The types that do not require a GitHub username.
_EXPECTED_NO_USERNAME = {
    SubmissionType.DEPLOYED_API,
    SubmissionType.CAREER_REFLECTION,
}

# Every submission type now has an active validator descriptor.
_ACTIVE_TYPES = {member.value for member in SubmissionType}


@pytest.mark.parametrize(
    "submission_type",
    sorted(
        set(SubmissionType) - _EXPECTED_NO_USERNAME,
        key=lambda t: t.value,
    ),
)
def test_requires_username_true_except_free_form(submission_type):
    descriptor = descriptor_for(submission_type)
    assert descriptor is not None
    assert descriptor.requires_username is True


@pytest.mark.parametrize(
    "submission_type", sorted(_EXPECTED_NO_USERNAME, key=lambda t: t.value)
)
def test_free_form_types_do_not_require_username(submission_type):
    descriptor = descriptor_for(submission_type)
    assert descriptor is not None
    assert descriptor.requires_username is False


def test_deployment_architecture_needs_username():
    descriptor = descriptor_for(SubmissionType.DEPLOYMENT_ARCHITECTURE)
    assert descriptor is not None
    assert descriptor.requires_username is True


def test_registry_covers_every_active_submission_type_exactly_once():
    """Completeness: each active type has exactly one descriptor, no extras.

    ``_ACTIVE_TYPES`` is derived from the full SubmissionType enum, so adding a
    real type without registering it fails here.
    """
    registry_values = {t.value for t in _VALIDATOR_REGISTRY}
    assert registry_values == _ACTIVE_TYPES
