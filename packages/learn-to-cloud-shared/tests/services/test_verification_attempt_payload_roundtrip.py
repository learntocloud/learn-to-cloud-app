"""Unit tests for verification attempt payload round-trips."""

from __future__ import annotations

from uuid import uuid4

import pytest

from learn_to_cloud_shared.submission_values import SubmittedValue
from learn_to_cloud_shared.testing.requirement_factories import (
    deployed_api_requirement,
    profile_readme_requirement,
    repo_fork_requirement,
)
from learn_to_cloud_shared.verification_workflow import PreparedVerificationAttempt


@pytest.mark.unit
class TestPreparedVerificationAttemptRoundTrip:
    def test_repo_fork_requirement_round_trip(self) -> None:
        requirement = repo_fork_requirement(slug="my-fork", required_repo="owner/repo")
        attempt = PreparedVerificationAttempt(
            id=uuid4(),
            user_id=42,
            github_username="alice",
            requirement=requirement,
            submitted_value=SubmittedValue.from_raw(
                requirement, "https://github.com/alice/repo"
            ),
        )
        payload = attempt.to_payload()
        assert "submitted_value" not in payload
        assert "submitted_value" not in payload["submission_value"]
        restored = PreparedVerificationAttempt.from_payload(payload)
        assert restored.requirement.slug == attempt.requirement.slug
        assert restored.requirement.type_config.required_repo == "owner/repo"
        assert type(restored.requirement) is type(attempt.requirement)

    def test_profile_readme_requirement_round_trip(self) -> None:
        requirement = profile_readme_requirement(slug="profile")
        attempt = PreparedVerificationAttempt(
            id=uuid4(),
            user_id=1,
            github_username="bob",
            requirement=requirement,
            submitted_value=SubmittedValue.from_raw(
                requirement, "https://github.com/bob/bob"
            ),
        )
        payload = attempt.to_payload()
        restored = PreparedVerificationAttempt.from_payload(payload)
        assert restored.requirement.slug == "profile"
        assert type(restored.requirement) is type(attempt.requirement)

    def test_deployed_api_requirement_round_trip(self) -> None:
        requirement = deployed_api_requirement(
            slug="deployed", placeholder="https://your-api.example.com"
        )
        attempt = PreparedVerificationAttempt(
            id=uuid4(),
            user_id=99,
            github_username=None,
            requirement=requirement,
            submitted_value=SubmittedValue.from_raw(
                requirement, "https://api.example.com"
            ),
        )
        payload = attempt.to_payload()
        restored = PreparedVerificationAttempt.from_payload(payload)
        assert restored.github_username is None
        assert (
            restored.requirement.type_config.placeholder
            == "https://your-api.example.com"
        )
