"""Unit tests for hands_on_verification_service.

Tests the submission routing logic in validate_submission():
- NETWORKING_TOKEN routes to networking_lab_service
- REPO_FORK routes to github_hands_on_verification_service
- Missing username handling for GitHub-dependent types
- Unknown submission type handling
- Evidence URL validation for deployment types
"""

from unittest.mock import AsyncMock, patch

import pytest

from models import SubmissionType
from schemas import HandsOnRequirement, ValidationResult
from services.hands_on_verification_service import (
    validate_submission,
)


def _make_requirement(
    submission_type: SubmissionType,
    required_repo: str | None = None,
    phase_id: int = 2,
    requirement_id: str = "test-req",
) -> HandsOnRequirement:
    """Helper to create test requirements."""
    return HandsOnRequirement(
        id=requirement_id,
        phase_id=phase_id,
        submission_type=submission_type,
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
            "services.hands_on_verification_service.validate_networking_token_submission"
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
            "services.github_hands_on_verification_service.validate_repo_fork",
            new_callable=AsyncMock,
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
                expected_username="testuser",
            )

            mock.assert_called_once_with(
                "https://github.com/testuser/networking-lab",
                "testuser",
                "learntocloud/networking-lab",
            )
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
        """REPO_FORK should fail if required_repo is missing from config."""
        requirement = _make_requirement(
            SubmissionType.REPO_FORK,
            required_repo=None,  # Missing config
        )

        result = await validate_submission(
            requirement=requirement,
            submitted_value="https://github.com/testuser/networking-lab",
            expected_username="testuser",
        )

        assert result.is_valid is False
        assert "configuration error" in result.message.lower()


@pytest.mark.unit
class TestSubmissionRouting:
    """Tests for submission routing to verification services."""

    @pytest.mark.asyncio
    async def test_deployed_api_routes_to_verification_service(self):
        """DEPLOYED_API type should route to deployed_api_verification_service."""
        requirement = _make_requirement(
            SubmissionType.DEPLOYED_API,
            phase_id=4,
        )

        with patch(
            "services.deployed_api_verification_service.validate_deployed_api",
            new_callable=AsyncMock,
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
            phase_id=5,
        )

        with patch(
            "services.devops_verification_service.analyze_devops_repository",
            new_callable=AsyncMock,
        ) as mock:
            mock.return_value = ValidationResult(
                is_valid=True, message="All DevOps tasks verified!"
            )

            result = await validate_submission(
                requirement=requirement,
                submitted_value="https://github.com/testuser/journal-starter",
                expected_username="testuser",
            )

            mock.assert_called_once_with(
                "https://github.com/testuser/journal-starter", "testuser"
            )
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
            SubmissionType.CODE_ANALYSIS,
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
        requirement = _make_requirement(SubmissionType.DEPLOYED_API, phase_id=4)

        with patch(
            "services.deployed_api_verification_service.validate_deployed_api",
            new_callable=AsyncMock,
        ) as mock:
            mock.return_value = ValidationResult(is_valid=True, message="API verified!")

            result = await validate_submission(
                requirement=requirement,
                submitted_value="https://api.example.com",
                expected_username=None,  # No username provided
            )

            # Should succeed - DEPLOYED_API doesn't require GitHub auth
            assert result.is_valid is True
