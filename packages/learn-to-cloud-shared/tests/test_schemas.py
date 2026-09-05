"""Unit tests for schema-derived constants."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from learn_to_cloud_shared.models import User
from learn_to_cloud_shared.schemas import (
    KNOWN_HANDS_ON_SUBMISSION_TYPES,
    CtfTokenConfig,
    UserResponse,
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


@pytest.mark.parametrize("name", [None, "  李 e\u0301  🛰️  ", "名" * 600])
def test_user_response_preserves_profile_and_contract(name) -> None:
    user = User(
        id=42,
        github_username="testuser",
        display_name=name,
        avatar_url=None,
        is_admin=False,
        created_at=datetime(2024, 1, 1, tzinfo=UTC),
    )
    response = UserResponse.model_validate(user)
    assert response.model_dump(mode="json") == {
        "id": 42,
        "github_username": "testuser",
        "display_name": name,
        "avatar_url": None,
        "is_admin": False,
        "created_at": "2024-01-01T00:00:00Z",
    }
    assert set(UserResponse.model_json_schema()["properties"]) == set(
        response.model_dump()
    )
    assert UserResponse.model_json_schema()["properties"]["display_name"]["anyOf"] == [
        {"type": "string"},
        {"type": "null"},
    ]
    with pytest.raises(ValidationError, match="frozen"):
        response.display_name = "Changed"
