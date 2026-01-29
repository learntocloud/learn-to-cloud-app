"""Tests for submissions service.

Contains both unit tests (helper functions) and integration tests (database operations).
"""

from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from models import SubmissionType
from services.submissions_service import (
    GitHubUsernameRequiredError,
    RequirementNotFoundError,
    get_validated_ids_by_phase,
    submit_validation,
)
from tests.factories import SubmissionFactory, UserFactory


class TestGetValidatedIdsByPhase:
    """Tests for get_validated_ids_by_phase helper function."""

    def test_empty_submissions_returns_empty_dict(self):
        """Test that empty submissions returns empty dict."""
        result = get_validated_ids_by_phase([])
        assert result == {}

    def test_groups_validated_submissions_by_phase(self):
        """Test that validated submissions are grouped by phase."""
        # Create mock submissions
        sub1 = SubmissionFactory.build(
            phase_id=1,
            requirement_id="phase1-req1",
            is_validated=True,
        )
        sub2 = SubmissionFactory.build(
            phase_id=1,
            requirement_id="phase1-req2",
            is_validated=True,
        )
        sub3 = SubmissionFactory.build(
            phase_id=2,
            requirement_id="phase2-req1",
            is_validated=True,
        )

        result = get_validated_ids_by_phase([sub1, sub2, sub3])

        assert 1 in result
        assert 2 in result
        assert "phase1-req1" in result[1]
        assert "phase1-req2" in result[1]
        assert "phase2-req1" in result[2]

    def test_excludes_non_validated_submissions(self):
        """Test that non-validated submissions are excluded."""
        validated = SubmissionFactory.build(
            phase_id=1,
            requirement_id="phase1-validated",
            is_validated=True,
        )
        not_validated = SubmissionFactory.build(
            phase_id=1,
            requirement_id="phase1-not-validated",
            is_validated=False,
        )

        result = get_validated_ids_by_phase([validated, not_validated])

        assert "phase1-validated" in result[1]
        assert "phase1-not-validated" not in result[1]


class TestSubmitValidation:
    """Tests for submit_validation."""

    @pytest.fixture
    async def user(self, db_session: AsyncSession):
        """Create a test user with GitHub username."""
        user = UserFactory.build(github_username="testuser")
        db_session.add(user)
        await db_session.flush()
        return user

    async def test_raises_for_unknown_requirement(self, db_session: AsyncSession, user):
        """Test that unknown requirement ID raises RequirementNotFoundError."""
        with pytest.raises(RequirementNotFoundError):
            await submit_validation(
                db_session,
                user.id,
                "nonexistent-requirement-id",
                "https://github.com/user/repo",
                user.github_username,
            )

    async def test_raises_when_github_username_required_but_missing(
        self, db_session: AsyncSession
    ):
        """Test that missing GitHub username raises GitHubUsernameRequiredError."""
        # Create user without GitHub username
        user = UserFactory.build(github_username=None)
        db_session.add(user)
        await db_session.flush()

        # Use a requirement that requires GitHub username
        from services.phase_requirements_service import get_requirements_for_phase

        reqs = get_requirements_for_phase(1)
        github_req = next(
            (
                r
                for r in reqs
                if r.submission_type
                in (
                    SubmissionType.PROFILE_README,
                    SubmissionType.REPO_FORK,
                    SubmissionType.CTF_TOKEN,
                )
            ),
            None,
        )

        if not github_req:
            pytest.skip("No GitHub-requiring requirement found")

        assert github_req is not None
        with pytest.raises(GitHubUsernameRequiredError):
            await submit_validation(
                db_session,
                user.id,
                github_req.id,
                "https://github.com/someuser/somerepo",
                None,  # No GitHub username
            )

    @patch("services.submissions_service.validate_submission")
    async def test_successful_validation(
        self, mock_validate, db_session: AsyncSession, user
    ):
        """Test successful submission validation."""
        from services.phase_requirements_service import get_requirements_for_phase

        # Find a GitHub profile requirement (doesn't require username)
        reqs = get_requirements_for_phase(0)
        profile_req = next(
            (r for r in reqs if r.submission_type == SubmissionType.GITHUB_PROFILE),
            None,
        )

        if not profile_req:
            pytest.skip("No GitHub profile requirement found")

        # Mock validation result
        mock_validate.return_value = AsyncMock(
            is_valid=True,
            message="Valid GitHub profile",
            username_match=True,
            repo_exists=None,
            task_results=None,
            server_error=False,
        )

        assert profile_req is not None
        assert user.github_username is not None
        result = await submit_validation(
            db_session,
            user.id,
            profile_req.id,
            f"https://github.com/{user.github_username}",
            user.github_username,
        )

        assert result.is_valid is True
        assert result.submission is not None
        assert result.submission.requirement_id == profile_req.id

    @patch("services.submissions_service.validate_submission")
    async def test_failed_validation(
        self, mock_validate, db_session: AsyncSession, user
    ):
        """Test failed submission validation."""
        from services.phase_requirements_service import get_requirements_for_phase

        reqs = get_requirements_for_phase(0)
        profile_req = next(
            (r for r in reqs if r.submission_type == SubmissionType.GITHUB_PROFILE),
            None,
        )

        if not profile_req:
            pytest.skip("No GitHub profile requirement found")

        # Mock failed validation
        mock_validate.return_value = AsyncMock(
            is_valid=False,
            message="Profile not found",
            username_match=False,
            repo_exists=None,
            task_results=None,
            server_error=False,
        )

        assert profile_req is not None
        assert user.github_username is not None
        result = await submit_validation(
            db_session,
            user.id,
            profile_req.id,
            "https://github.com/nonexistent-user-xyz",
            user.github_username,
        )

        assert result.is_valid is False
        assert result.submission is not None
        assert result.submission.is_validated is False

    @patch("services.submissions_service.validate_submission")
    async def test_upsert_updates_existing_submission(
        self, mock_validate, db_session: AsyncSession, user
    ):
        """Test that resubmitting updates existing submission."""
        from services.phase_requirements_service import get_requirements_for_phase

        reqs = get_requirements_for_phase(0)
        profile_req = next(
            (r for r in reqs if r.submission_type == SubmissionType.GITHUB_PROFILE),
            None,
        )

        if not profile_req:
            pytest.skip("No GitHub profile requirement found")

        mock_validate.return_value = AsyncMock(
            is_valid=True,
            message="Valid",
            username_match=True,
            repo_exists=None,
            task_results=None,
            server_error=False,
        )

        assert profile_req is not None
        assert user.github_username is not None
        # First submission
        result1 = await submit_validation(
            db_session,
            user.id,
            profile_req.id,
            f"https://github.com/{user.github_username}",
            user.github_username,
        )

        # Second submission (update)
        result2 = await submit_validation(
            db_session,
            user.id,
            profile_req.id,
            f"https://github.com/{user.github_username}",
            user.github_username,
        )

        # Should be the same submission ID (upserted)
        assert result1.submission.id == result2.submission.id


class TestRequirementNotFoundError:
    """Tests for RequirementNotFoundError."""

    def test_exception_message(self):
        """Test exception contains the requirement ID."""
        exc = RequirementNotFoundError("Requirement not found: test-id")
        assert "test-id" in str(exc)


class TestGitHubUsernameRequiredError:
    """Tests for GitHubUsernameRequiredError."""

    def test_exception_message(self):
        """Test exception has appropriate message."""
        exc = GitHubUsernameRequiredError("GitHub username required")
        assert "GitHub" in str(exc)
