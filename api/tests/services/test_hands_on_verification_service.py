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

from models import SubmissionType
from schemas import HandsOnRequirement, ValidationResult
from services.hands_on_verification_service import (
    validate_submission,
)


def _make_requirement(
    submission_type: SubmissionType,
    required_repo: str | None = None,
    requirement_id: str = "test-req",
) -> HandsOnRequirement:
    """Helper to create test requirements."""
    return HandsOnRequirement(
        id=requirement_id,
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
            "services.hands_on_verification_service.validate_networking_token_submission",
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
            "services.github_hands_on_verification_service.validate_repo_fork",
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
        )

        with patch(
            "services.deployed_api_verification_service.validate_deployed_api",
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
    async def test_pr_review_routes_to_pr_service(self):
        """PR_REVIEW type should route to pr_verification_service."""
        requirement = HandsOnRequirement(
            id="journal-pr-logging",
            submission_type=SubmissionType.PR_REVIEW,
            name="PR: Logging Setup",
            description="Test",
            expected_files=["api/main.py"],
        )

        with patch(
            "services.pr_verification_service.validate_pr",
            autospec=True,
        ) as mock:
            mock.return_value = ValidationResult(
                is_valid=True,
                message="PR #1 verified!",
                username_match=True,
            )

            result = await validate_submission(
                requirement=requirement,
                submitted_value="https://github.com/testuser/journal-starter/pull/1",
                expected_username="testuser",
            )

            mock.assert_called_once_with(
                "https://github.com/testuser/journal-starter/pull/1",
                "testuser",
                requirement,
            )
            assert result.is_valid is True

    @pytest.mark.asyncio
    async def test_devops_analysis_routes_to_devops_service(self):
        """DEVOPS_ANALYSIS type should route to devops_verification_service."""
        requirement = _make_requirement(
            SubmissionType.DEVOPS_ANALYSIS,
        )

        with patch(
            "services.devops_verification_service.analyze_devops_repository",
            autospec=True,
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
            SubmissionType.PR_REVIEW,
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
        requirement = _make_requirement(SubmissionType.DEPLOYED_API)

        with patch(
            "services.deployed_api_verification_service.validate_deployed_api",
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
# Token submission wrappers
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestValidateCtfTokenSubmission:
    def test_delegates_to_ctf_service(self):
        from unittest.mock import MagicMock

        from services.hands_on_verification_service import (
            validate_ctf_token_submission,
        )

        mock_result = MagicMock()
        mock_result.is_valid = True
        mock_result.message = "OK"
        mock_result.server_error = False
        with patch(
            "services.ctf_service.verify_ctf_token",
            autospec=True,
            return_value=mock_result,
        ) as mock:
            result = validate_ctf_token_submission("token", "testuser")
        mock.assert_called_once_with("token", "testuser")
        assert result.is_valid is True


@pytest.mark.unit
class TestValidateNetworkingTokenSubmission:
    def test_extracts_cloud_provider(self):
        from unittest.mock import MagicMock

        from services.hands_on_verification_service import (
            validate_networking_token_submission,
        )

        mock_result = MagicMock()
        mock_result.is_valid = True
        mock_result.message = "OK"
        mock_result.server_error = False
        mock_result.challenge_type = "networking-lab-azure"
        with patch(
            "services.networking_lab_service.verify_networking_token",
            autospec=True,
            return_value=mock_result,
        ):
            result = validate_networking_token_submission("token", "testuser")
        assert result.cloud_provider == "azure"

    def test_no_cloud_provider_when_invalid(self):
        from unittest.mock import MagicMock

        from services.hands_on_verification_service import (
            validate_networking_token_submission,
        )

        mock_result = MagicMock()
        mock_result.is_valid = False
        mock_result.message = "bad"
        mock_result.server_error = False
        mock_result.challenge_type = None
        with patch(
            "services.networking_lab_service.verify_networking_token",
            autospec=True,
            return_value=mock_result,
        ):
            result = validate_networking_token_submission("token", "testuser")
        assert result.cloud_provider is None


# ---------------------------------------------------------------------------
# Dispatch branches not covered by existing tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestDispatchGitHubProfile:
    @pytest.mark.asyncio
    async def test_github_profile_routes_correctly(self):
        requirement = _make_requirement(SubmissionType.GITHUB_PROFILE)
        with patch(
            "services.github_hands_on_verification_service.validate_github_profile",
            autospec=True,
        ) as mock:
            mock.return_value = ValidationResult(is_valid=True, message="Verified!")
            result = await validate_submission(
                requirement=requirement,
                submitted_value="https://github.com/testuser",
                expected_username="testuser",
            )
        mock.assert_called_once_with("https://github.com/testuser", "testuser")
        assert result.is_valid is True


@pytest.mark.unit
class TestDispatchSecurityScanning:
    @pytest.mark.asyncio
    async def test_security_scanning_routes_correctly(self):
        requirement = _make_requirement(SubmissionType.SECURITY_SCANNING)
        with patch(
            "services.security_verification_service.validate_security_scanning",
            autospec=True,
        ) as mock:
            mock.return_value = ValidationResult(is_valid=True, message="Scanned!")
            result = await validate_submission(
                requirement=requirement,
                submitted_value="https://github.com/testuser/repo",
                expected_username="testuser",
            )
        mock.assert_called_once_with("https://github.com/testuser/repo", "testuser")
        assert result.is_valid is True
