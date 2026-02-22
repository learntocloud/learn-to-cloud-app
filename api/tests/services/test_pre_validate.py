"""Unit tests for pre_validate_submission.

Tests cover:
- Requirement not found → RequirementNotFoundError
- Already validated → AlreadyValidatedError
- GitHub username required → GitHubUsernameRequiredError
"""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.submissions_service import (
    AlreadyValidatedError,
    GitHubUsernameRequiredError,
    RequirementNotFoundError,
    pre_validate_submission,
)


def _mock_session_maker():
    """Create a mock async_sessionmaker."""

    @asynccontextmanager
    async def _factory():
        yield AsyncMock()

    return _factory


@pytest.mark.unit
class TestPreValidateSubmission:
    """Tests for the pre-validation fast path."""

    @pytest.mark.asyncio
    async def test_raises_requirement_not_found(self):
        """Unknown requirement raises RequirementNotFoundError."""
        with patch(
            "services.submissions_service.get_requirement_by_id",
            return_value=None,
        ):
            with pytest.raises(RequirementNotFoundError):
                await pre_validate_submission(
                    session_maker=_mock_session_maker(),
                    user_id=1,
                    requirement_id="nonexistent",
                    submitted_value="https://github.com/user/repo",
                    github_username="user",
                )

    @pytest.mark.asyncio
    async def test_raises_already_validated(self):
        """Already-validated requirement raises AlreadyValidatedError."""
        mock_req = MagicMock()
        mock_req.submission_type = "code_analysis"

        mock_existing = MagicMock()
        mock_existing.is_validated = True

        with patch(
            "services.submissions_service.get_requirement_by_id",
            return_value=mock_req,
        ), patch(
            "services.submissions_service.get_phase_id_for_requirement",
            return_value=3,
        ), patch(
            "services.submissions_service.SubmissionRepository",
        ) as MockRepo:
            repo = MockRepo.return_value
            repo.get_by_user_and_requirement = AsyncMock(return_value=mock_existing)

            with pytest.raises(AlreadyValidatedError):
                await pre_validate_submission(
                    session_maker=_mock_session_maker(),
                    user_id=1,
                    requirement_id="req-1",
                    submitted_value="https://github.com/user/repo",
                    github_username="user",
                )

    @pytest.mark.asyncio
    async def test_raises_github_username_required(self):
        """Missing GitHub username for code_analysis raises error."""
        mock_req = MagicMock()
        mock_req.submission_type = "code_analysis"

        with patch(
            "services.submissions_service.get_requirement_by_id",
            return_value=mock_req,
        ), patch(
            "services.submissions_service.get_phase_id_for_requirement",
            return_value=3,
        ), patch(
            "services.submissions_service.get_prerequisite_phase",
            return_value=None,
        ), patch(
            "services.submissions_service.SubmissionRepository",
        ) as MockRepo:
            repo = MockRepo.return_value
            repo.get_by_user_and_requirement = AsyncMock(return_value=None)
            repo.count_submissions_today = AsyncMock(return_value=0)
            repo.get_last_submission_time = AsyncMock(return_value=None)

            with pytest.raises(GitHubUsernameRequiredError):
                await pre_validate_submission(
                    session_maker=_mock_session_maker(),
                    user_id=1,
                    requirement_id="req-1",
                    submitted_value="https://github.com/user/repo",
                    github_username=None,
                )
