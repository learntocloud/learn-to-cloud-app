"""Tests for the hands-on verification service module.

Tests validation routing for Phase 0 and Phase 1 submission types:
- GitHub Profile (Phase 0)
- Profile README (Phase 1)
- Repository Fork (Phase 1)
- CTF Token (Phase 1)
"""

from unittest.mock import patch

import pytest

from models import SubmissionType
from schemas import HandsOnRequirement, ValidationResult


class TestValidateSubmission:
    """Tests for validate_submission routing function."""

    @pytest.mark.asyncio
    async def test_github_profile_routing(self):
        """GitHub profile submission should route to validate_github_profile."""
        from services.hands_on_verification_service import validate_submission

        requirement = HandsOnRequirement(
            id="test-profile",
            phase_id=0,
            submission_type=SubmissionType.GITHUB_PROFILE,
            name="Test Profile",
            description="Test",
        )

        with patch(
            "services.hands_on_verification_service.validate_github_profile"
        ) as mock:
            mock.return_value = ValidationResult(
                is_valid=True, message="Profile verified"
            )

            result = await validate_submission(
                requirement,
                "https://github.com/testuser",
                expected_username="testuser",
            )

            mock.assert_called_once_with("https://github.com/testuser", "testuser")
            assert result.is_valid is True

    @pytest.mark.asyncio
    async def test_github_profile_missing_username(self):
        """GitHub profile without username should fail."""
        from services.hands_on_verification_service import validate_submission

        requirement = HandsOnRequirement(
            id="test-profile",
            phase_id=0,
            submission_type=SubmissionType.GITHUB_PROFILE,
            name="Test Profile",
            description="Test",
        )

        result = await validate_submission(
            requirement,
            "https://github.com/testuser",
            expected_username=None,
        )

        assert result.is_valid is False
        assert "GitHub username is required" in result.message

    @pytest.mark.asyncio
    async def test_profile_readme_routing(self):
        """Profile README submission should route to validate_profile_readme."""
        from services.hands_on_verification_service import validate_submission

        requirement = HandsOnRequirement(
            id="test-readme",
            phase_id=1,
            submission_type=SubmissionType.PROFILE_README,
            name="Test README",
            description="Test",
        )

        with patch(
            "services.hands_on_verification_service.validate_profile_readme"
        ) as mock:
            mock.return_value = ValidationResult(
                is_valid=True, message="README verified"
            )

            result = await validate_submission(
                requirement,
                "https://github.com/testuser/testuser/blob/main/README.md",
                expected_username="testuser",
            )

            mock.assert_called_once()
            assert result.is_valid is True

    @pytest.mark.asyncio
    async def test_profile_readme_missing_username(self):
        """Profile README without username should fail."""
        from services.hands_on_verification_service import validate_submission

        requirement = HandsOnRequirement(
            id="test-readme",
            phase_id=1,
            submission_type=SubmissionType.PROFILE_README,
            name="Test README",
            description="Test",
        )

        result = await validate_submission(
            requirement,
            "https://github.com/testuser/testuser/blob/main/README.md",
            expected_username=None,
        )

        assert result.is_valid is False
        assert "GitHub username is required" in result.message

    @pytest.mark.asyncio
    async def test_repo_fork_routing(self):
        """Repo fork submission should route to validate_repo_fork."""
        from services.hands_on_verification_service import validate_submission

        requirement = HandsOnRequirement(
            id="test-fork",
            phase_id=1,
            submission_type=SubmissionType.REPO_FORK,
            name="Test Fork",
            description="Test",
            required_repo="original/repo",
        )

        with patch("services.hands_on_verification_service.validate_repo_fork") as mock:
            mock.return_value = ValidationResult(is_valid=True, message="Fork verified")

            result = await validate_submission(
                requirement,
                "https://github.com/testuser/repo",
                expected_username="testuser",
            )

            mock.assert_called_once_with(
                "https://github.com/testuser/repo", "testuser", "original/repo"
            )
            assert result.is_valid is True

    @pytest.mark.asyncio
    async def test_repo_fork_missing_username(self):
        """Repo fork without username should fail."""
        from services.hands_on_verification_service import validate_submission

        requirement = HandsOnRequirement(
            id="test-fork",
            phase_id=1,
            submission_type=SubmissionType.REPO_FORK,
            name="Test Fork",
            description="Test",
            required_repo="original/repo",
        )

        result = await validate_submission(
            requirement,
            "https://github.com/testuser/repo",
            expected_username=None,
        )

        assert result.is_valid is False
        assert "GitHub username is required" in result.message

    @pytest.mark.asyncio
    async def test_repo_fork_missing_required_repo(self):
        """Repo fork without required_repo config should fail."""
        from services.hands_on_verification_service import validate_submission

        requirement = HandsOnRequirement(
            id="test-fork",
            phase_id=1,
            submission_type=SubmissionType.REPO_FORK,
            name="Test Fork",
            description="Test",
            required_repo=None,
        )

        result = await validate_submission(
            requirement,
            "https://github.com/testuser/repo",
            expected_username="testuser",
        )

        assert result.is_valid is False
        assert "missing required_repo" in result.message

    @pytest.mark.asyncio
    async def test_ctf_token_routing(self):
        """CTF token submission should route to validate_ctf_token_submission."""
        from services.hands_on_verification_service import validate_submission

        requirement = HandsOnRequirement(
            id="test-ctf",
            phase_id=1,
            submission_type=SubmissionType.CTF_TOKEN,
            name="Test CTF",
            description="Test",
        )

        with patch("services.hands_on_verification_service.verify_ctf_token") as mock:
            mock.return_value = ValidationResult(is_valid=True, message="CTF verified")

            result = await validate_submission(
                requirement,
                "some-ctf-token",
                expected_username="testuser",
            )

            mock.assert_called_once_with("some-ctf-token", "testuser")
            assert result.is_valid is True

    @pytest.mark.asyncio
    async def test_ctf_token_missing_username(self):
        """CTF token without username should fail."""
        from services.hands_on_verification_service import validate_submission

        requirement = HandsOnRequirement(
            id="test-ctf",
            phase_id=1,
            submission_type=SubmissionType.CTF_TOKEN,
            name="Test CTF",
            description="Test",
        )

        result = await validate_submission(
            requirement,
            "some-ctf-token",
            expected_username=None,
        )

        assert result.is_valid is False
        assert "GitHub username is required" in result.message


class TestValidateCtfTokenSubmission:
    """Tests for validate_ctf_token_submission function."""

    def test_valid_ctf_token(self):
        """Valid CTF token should pass."""
        from services.hands_on_verification_service import validate_ctf_token_submission

        with patch("services.hands_on_verification_service.verify_ctf_token") as mock:
            mock.return_value = ValidationResult(
                is_valid=True, message="All challenges completed"
            )

            result = validate_ctf_token_submission("valid-token", "testuser")

            assert result.is_valid is True
            assert result.username_match is True

    def test_invalid_ctf_token(self):
        """Invalid CTF token should fail."""
        from services.hands_on_verification_service import validate_ctf_token_submission

        with patch("services.hands_on_verification_service.verify_ctf_token") as mock:
            mock.return_value = ValidationResult(
                is_valid=False, message="Invalid token"
            )

            result = validate_ctf_token_submission("invalid-token", "testuser")

            assert result.is_valid is False
            assert result.username_match is False
