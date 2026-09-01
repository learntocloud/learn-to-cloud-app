"""Unit tests for schema-derived constants."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from learn_to_cloud_shared.schemas import (
    KNOWN_HANDS_ON_SUBMISSION_TYPES,
    CtfTokenConfig,
)


def test_known_submission_types_matches_union() -> None:
    """The derived constant must list exactly the union's submission types."""
    assert KNOWN_HANDS_ON_SUBMISSION_TYPES == {
        "profile_readme",
        "repo_fork",
        "ctf_token",
        "networking_token",
        "journal_api_verifier",
        "deployed_api",
        "devops_analysis",
        "security_scanning",
        "career_reflection",
        "deployment_architecture",
    }
    # A type the DB CHECK allows but the union doesn't know must be absent,
    # so the content loader treats it as unknown (issue #603).
    assert "ci_status" not in KNOWN_HANDS_ON_SUBMISSION_TYPES


def test_input_length_range_must_be_ordered() -> None:
    with pytest.raises(ValidationError, match="min_length cannot exceed max_length"):
        CtfTokenConfig(min_length=200, max_length=100)
