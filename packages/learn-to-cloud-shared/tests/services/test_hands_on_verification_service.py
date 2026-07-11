"""Unit tests for hands_on_verification_service.

Tests the submission routing logic in validate_submission():
- NETWORKING_TOKEN routes to networking_lab_service
- REPO_FORK routes to github_hands_on_verification_service
- Missing username handling for GitHub-dependent types
- Unknown submission type handling
- Evidence URL validation for deployment types
"""

from unittest.mock import patch

import pytest

from learn_to_cloud_shared.models import SubmissionType
from learn_to_cloud_shared.schemas import HandsOnRequirement, ValidationResult
from learn_to_cloud_shared.submission_derivation import build_target
from learn_to_cloud_shared.verification.dispatcher import (
    validate_submission,
)


def _make_requirement(
    submission_type: SubmissionType,
    required_repo: str | None = None,
    requirement_id: str = "test-req",
) -> HandsOnRequirement:
    """Helper to create test requirements."""
    from learn_to_cloud_shared.testing.requirement_factories import make_requirement

    return make_requirement(
        submission_type,
        slug=requirement_id,
        name="Test Requirement",
        description="Test description",
        required_repo=required_repo,
    )


@pytest.mark.unit
class TestValidateSubmissionRouting:
    """Tests that validate_submission routes to the correct validator."""

    @pytest.mark.asyncio
    async def test_networking_token_routes_correctly(self):
        """NETWORKING_TOKEN should route to networking_lab_service."""
        requirement = _make_requirement(SubmissionType.NETWORKING_TOKEN)

        with patch(
            "learn_to_cloud_shared.verification.dispatcher.verify_networking_token",
            autospec=True,
        ) as mock:
            mock.return_value = ValidationResult(
                is_valid=True, message="Token verified!"
            )

            result = await validate_submission(
                requirement=requirement,
                submitted_value="test-token",
                expected_username="testuser",
            )

            mock.assert_called_once_with("test-token", "testuser")
            assert result.is_valid is True

    @pytest.mark.asyncio
    async def test_networking_token_requires_username(self):
        """NETWORKING_TOKEN should fail without username."""
        requirement = _make_requirement(SubmissionType.NETWORKING_TOKEN)

        result = await validate_submission(
            requirement=requirement,
            submitted_value="test-token",
            expected_username=None,
        )

        assert result.is_valid is False
        assert "GitHub username is required" in result.message

    @pytest.mark.asyncio
    async def test_repo_fork_routes_correctly(self):
        """REPO_FORK should route to validate_repo_fork."""
        requirement = _make_requirement(
            SubmissionType.REPO_FORK,
            required_repo="learntocloud/networking-lab",
        )

        with patch(
            "learn_to_cloud_shared.verification.dispatcher.validate_repo_fork",
            autospec=True,
        ) as mock:
            mock.return_value = ValidationResult(
                is_valid=True,
                message="Fork verified!",
                username_match=True,
                repo_exists=True,
            )

            result = await validate_submission(
                requirement=requirement,
                submitted_value="https://github.com/testuser/networking-lab",
                target=build_target(requirement, "testuser"),
                expected_username="testuser",
            )

            mock.assert_called_once_with(build_target(requirement, "testuser"))
            assert result.is_valid is True

    @pytest.mark.asyncio
    async def test_repo_fork_requires_username(self):
        """REPO_FORK should fail without username."""
        requirement = _make_requirement(
            SubmissionType.REPO_FORK,
            required_repo="learntocloud/networking-lab",
        )

        result = await validate_submission(
            requirement=requirement,
            submitted_value="https://github.com/testuser/networking-lab",
            expected_username=None,
        )

        assert result.is_valid is False
        assert "GitHub username is required" in result.message

    @pytest.mark.asyncio
    async def test_repo_fork_requires_required_repo_config(self):
        """RepoForkConfig.required_repo is required at Pydantic level (#470).

        The earlier behavior was: dispatcher caught missing required_repo at
        runtime and returned a configuration error. After the discriminated
        union refactor, the schema rejects construction of a RepoForkRequirement
        without a required_repo, so this is now caught at YAML load time
        instead of dispatch time -- a strict improvement.
        """
        from pydantic import ValidationError

        from learn_to_cloud_shared.schemas import HandsOnRequirementAdapter

        # Construct via TypeAdapter with raw dict so static analysis
        # doesn't catch the deliberate validation error.
        with pytest.raises(ValidationError):
            HandsOnRequirementAdapter.validate_python(
                {
                    "uuid": "00000000-0000-0000-0000-000000000001",
                    "id": "repo-fork",
                    "submission_type": "repo_fork",
                    "name": "Test",
                    "description": "Test",
                    "type_config": {},
                }
            )


@pytest.mark.unit
class TestSubmissionRouting:
    """Tests for submission routing to verification services."""

    @pytest.mark.asyncio
    async def test_deployed_api_routes_to_verification_service(self):
        """DEPLOYED_API type should route to deployed_api_verification_service."""
        requirement = _make_requirement(
            SubmissionType.DEPLOYED_API,
        )

        with patch(
            "learn_to_cloud_shared.verification.dispatcher.validate_deployed_api",
            autospec=True,
        ) as mock:
            mock.return_value = ValidationResult(
                is_valid=True, message="Deployed API verified!"
            )

            result = await validate_submission(
                requirement=requirement,
                submitted_value="https://my-api.azurewebsites.net",
                expected_username="testuser",
            )

            mock.assert_called_once_with("https://my-api.azurewebsites.net")
            assert result.is_valid is True

    @pytest.mark.asyncio
    async def test_devops_analysis_routes_to_devops_service(self):
        """DEVOPS_ANALYSIS type should route to devops_verification_service."""
        requirement = _make_requirement(
            SubmissionType.DEVOPS_ANALYSIS,
            required_repo="learntocloud/journal-starter",
        )

        with patch(
            "learn_to_cloud_shared.verification.dispatcher.run_devops_workflow",
            autospec=True,
        ) as mock:
            mock.return_value = ValidationResult(
                is_valid=True, message="All DevOps tasks verified!"
            )

            result = await validate_submission(
                requirement=requirement,
                submitted_value="https://github.com/testuser/journal-starter",
                target=build_target(requirement, "testuser"),
                expected_username="testuser",
            )

            mock.assert_called_once_with("testuser", "journal-starter")
            assert result.is_valid is True


@pytest.mark.unit
class TestValidateSubmissionUsernameRequirements:
    """Tests that username is required for all GitHub-dependent types."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "submission_type",
        [
            SubmissionType.GITHUB_PROFILE,
            SubmissionType.PROFILE_README,
            SubmissionType.REPO_FORK,
            SubmissionType.CTF_TOKEN,
            SubmissionType.NETWORKING_TOKEN,
            SubmissionType.JOURNAL_API_VERIFIER,
            SubmissionType.DEVOPS_ANALYSIS,
            SubmissionType.SECURITY_SCANNING,
        ],
    )
    async def test_github_dependent_types_require_username(
        self, submission_type: SubmissionType
    ):
        """All GitHub-dependent submission types should fail without username."""
        requirement = _make_requirement(
            submission_type,
            required_repo="learntocloud/test-repo",  # For REPO_FORK
        )

        result = await validate_submission(
            requirement=requirement,
            submitted_value="https://github.com/testuser/repo",
            expected_username=None,
        )

        assert result.is_valid is False
        assert "username" in result.message.lower()

    @pytest.mark.asyncio
    async def test_deployed_api_doesnt_require_username(self):
        """DEPLOYED_API should not require username."""
        requirement = _make_requirement(SubmissionType.DEPLOYED_API)

        with patch(
            "learn_to_cloud_shared.verification.dispatcher.validate_deployed_api",
            autospec=True,
        ) as mock:
            mock.return_value = ValidationResult(is_valid=True, message="API verified!")

            result = await validate_submission(
                requirement=requirement,
                submitted_value="https://api.example.com",
                expected_username=None,  # No username provided
            )

            # Should succeed - DEPLOYED_API doesn't require GitHub auth
            assert result.is_valid is True


# ---------------------------------------------------------------------------
# Dispatch branches not covered by existing tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestDispatchGitHubProfile:
    @pytest.mark.asyncio
    async def test_github_profile_routes_correctly(self):
        requirement = _make_requirement(SubmissionType.GITHUB_PROFILE)
        with patch(
            "learn_to_cloud_shared.verification.dispatcher.validate_github_profile",
            autospec=True,
        ) as mock:
            mock.return_value = ValidationResult(is_valid=True, message="Verified!")
            result = await validate_submission(
                requirement=requirement,
                submitted_value="https://github.com/testuser",
                target=build_target(requirement, "testuser"),
                expected_username="testuser",
            )
        mock.assert_called_once_with(build_target(requirement, "testuser"))
        assert result.is_valid is True


@pytest.mark.unit
class TestDispatchSecurityScanning:
    @pytest.mark.asyncio
    async def test_security_scanning_routes_correctly(self):
        requirement = _make_requirement(
            SubmissionType.SECURITY_SCANNING,
            required_repo="learntocloud/journal-starter",
        )
        with patch(
            "learn_to_cloud_shared.verification.dispatcher.validate_security_scanning",
            autospec=True,
        ) as mock:
            mock.return_value = ValidationResult(is_valid=True, message="Scanned!")
            result = await validate_submission(
                requirement=requirement,
                submitted_value="https://github.com/testuser/journal-starter",
                target=build_target(requirement, "testuser"),
                expected_username="testuser",
            )
        mock.assert_called_once_with("testuser", "journal-starter")
        assert result.is_valid is True
