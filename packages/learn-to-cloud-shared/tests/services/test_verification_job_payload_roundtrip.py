"""Unit tests for PreparedVerificationJob payload round-trip (issue #470).

Durable verification jobs serialize a PreparedVerificationJob to a JSON
payload and rehydrate it later. After hoisting requirements into a
Pydantic discriminated union (#470), the rehydration path must use
HandsOnRequirementAdapter instead of HandsOnRequirement.model_validate
(unions are not BaseModels).
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from learn_to_cloud_shared.testing.requirement_factories import (
    deployed_api_requirement,
    profile_readme_requirement,
    repo_fork_requirement,
)
from learn_to_cloud_shared.verification_job_executor import PreparedVerificationJob


@pytest.mark.unit
class TestPreparedVerificationJobRoundTrip:
    def test_repo_fork_requirement_round_trip(self) -> None:
        job = PreparedVerificationJob(
            id=uuid4(),
            user_id=42,
            github_username="alice",
            requirement=repo_fork_requirement(
                slug="my-fork", required_repo="owner/repo"
            ),
            submitted_value="https://github.com/alice/repo",
        )
        payload = job.to_payload()
        restored = PreparedVerificationJob.from_payload(payload)
        assert restored.requirement.slug == job.requirement.slug
        assert restored.requirement.required_repo == "owner/repo"
        assert type(restored.requirement) is type(job.requirement)

    def test_profile_readme_requirement_round_trip(self) -> None:
        job = PreparedVerificationJob(
            id=uuid4(),
            user_id=1,
            github_username="bob",
            requirement=profile_readme_requirement(slug="profile"),
            submitted_value="https://github.com/bob/bob",
        )
        payload = job.to_payload()
        restored = PreparedVerificationJob.from_payload(payload)
        assert restored.requirement.slug == "profile"
        assert restored.requirement.required_repo is None

    def test_deployed_api_requirement_round_trip(self) -> None:
        job = PreparedVerificationJob(
            id=uuid4(),
            user_id=99,
            github_username=None,
            requirement=deployed_api_requirement(
                slug="deployed", placeholder="https://your-api.example.com"
            ),
            submitted_value="https://api.example.com",
        )
        payload = job.to_payload()
        restored = PreparedVerificationJob.from_payload(payload)
        assert restored.github_username is None
        assert restored.requirement.placeholder == "https://your-api.example.com"
