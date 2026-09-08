"""Unit tests for shared schema contracts."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from learn_to_cloud_shared.models import SubmissionType, User
from learn_to_cloud_shared.schemas import (
    CtfTokenConfig,
    HandsOnRequirementAdapter,
    UserResponse,
)


@pytest.mark.parametrize("submission_type", ["ci_status", "deployment_architecture"])
def test_unknown_submission_type_is_rejected(submission_type: str) -> None:
    with pytest.raises(ValidationError) as exc_info:
        HandsOnRequirementAdapter.validate_python({"submission_type": submission_type})
    assert [error["type"] for error in exc_info.value.errors()] == ["union_tag_invalid"]


def test_input_length_range_must_be_ordered() -> None:
    with pytest.raises(ValidationError, match="min_length cannot exceed max_length"):
        CtfTokenConfig(min_length=200, max_length=100)


@pytest.mark.parametrize(
    "submission_type",
    [
        SubmissionType.REPO_FORK,
        SubmissionType.JOURNAL_API_VERIFIER,
        SubmissionType.DEVOPS_ANALYSIS,
        SubmissionType.SECURITY_SCANNING,
    ],
)
def test_repo_requirement_requires_required_repo(
    submission_type: SubmissionType,
) -> None:
    required_repo = "learntocloud/journal-starter"
    payload = {
        "uuid": "00000000-0000-0000-0000-000000000001",
        "slug": "repo-check",
        "submission_type": submission_type.value,
        "name": "Repository check",
        "description": "Test",
        "type_config": {"required_repo": required_repo},
    }
    requirement = HandsOnRequirementAdapter.validate_python(payload)
    assert requirement.type_config.model_dump()["required_repo"] == required_repo

    payload["type_config"] = {}
    with pytest.raises(ValidationError) as exc_info:
        HandsOnRequirementAdapter.validate_python(payload)
    assert [(error["loc"], error["type"]) for error in exc_info.value.errors()] == [
        ((submission_type.value, "type_config", "required_repo"), "missing")
    ]


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
