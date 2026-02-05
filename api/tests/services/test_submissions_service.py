"""Tests for submissions_service cooldown enforcement.

Tests cover:
- Cooldown is enforced for CODE_ANALYSIS submissions
- Cooldown is enforced for other submission types
- Server errors exempt from cooldown (verification_completed=False)
- First submission always allowed (no prior record)
- Cooldown respects configured duration
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from models import SubmissionType
from schemas import HandsOnRequirement, ValidationResult
from services.submissions_service import (
    ConcurrentSubmissionError,
    CooldownActiveError,
    GitHubUsernameRequiredError,
    RequirementNotFoundError,
    _get_submission_lock,
    submit_validation,
)


def _make_mock_requirement(
    submission_type: SubmissionType = SubmissionType.CODE_ANALYSIS,
    phase_id: int = 3,
) -> HandsOnRequirement:
    """Create a mock requirement for testing."""
    return HandsOnRequirement(
        id="test-requirement",
        submission_type=submission_type,
        name="Test Requirement",
        description="Test description",
        phase_id=phase_id,
    )


@pytest.mark.unit
class TestCooldownEnforcement:
    """Tests for cooldown logic in submit_validation."""

    @pytest.mark.asyncio
    async def test_first_submission_allowed(self):
        """First submission should always be allowed (no cooldown)."""
        mock_db = AsyncMock()
        mock_requirement = _make_mock_requirement()

        with (
            patch(
                "services.submissions_service.get_requirement_by_id",
                return_value=mock_requirement,
            ),
            patch(
                "services.submissions_service.SubmissionRepository"
            ) as mock_repo_class,
            patch(
                "services.submissions_service.validate_submission",
                new_callable=AsyncMock,
            ) as mock_validate,
        ):
            mock_repo = MagicMock()
            mock_repo.get_last_submission_time = AsyncMock(return_value=None)
            mock_repo.upsert = AsyncMock(
                return_value=MagicMock(
                    id=1,
                    requirement_id="test-requirement",
                    submission_type=SubmissionType.CODE_ANALYSIS,
                    phase_id=3,
                    submitted_value="https://github.com/user/repo",
                    extracted_username="user",
                    is_validated=True,
                    validated_at=datetime.now(UTC),
                    verification_completed=True,
                    created_at=datetime.now(UTC),
                )
            )
            mock_repo_class.return_value = mock_repo

            mock_validate.return_value = ValidationResult(
                is_valid=True,
                message="All tasks passed",
            )

            # Should not raise - first submission allowed
            result = await submit_validation(
                db=mock_db,
                user_id="user-123",
                requirement_id="test-requirement",
                submitted_value="https://github.com/user/repo",
                github_username="user",
            )

            assert result.is_valid is True
            mock_validate.assert_called_once()

    @pytest.mark.asyncio
    async def test_cooldown_blocks_rapid_resubmission(self):
        """Submission within cooldown period should raise CooldownActiveError."""
        mock_db = AsyncMock()
        mock_requirement = _make_mock_requirement()

        # Last submission was 5 minutes ago (well within 1-hour cooldown)
        last_submission = datetime.now(UTC) - timedelta(minutes=5)

        with (
            patch(
                "services.submissions_service.get_requirement_by_id",
                return_value=mock_requirement,
            ),
            patch(
                "services.submissions_service.SubmissionRepository"
            ) as mock_repo_class,
            patch("services.submissions_service.get_settings") as mock_settings,
        ):
            mock_repo = MagicMock()
            mock_repo.get_last_submission_time = AsyncMock(return_value=last_submission)
            mock_repo_class.return_value = mock_repo

            mock_settings.return_value.code_analysis_cooldown_seconds = 3600
            mock_settings.return_value.submission_cooldown_seconds = 3600

            with pytest.raises(CooldownActiveError) as exc_info:
                await submit_validation(
                    db=mock_db,
                    user_id="user-123",
                    requirement_id="test-requirement",
                    submitted_value="https://github.com/user/repo",
                    github_username="user",
                )

            # Should have ~55 minutes remaining
            assert exc_info.value.retry_after_seconds > 3000
            assert exc_info.value.retry_after_seconds <= 3600

    @pytest.mark.asyncio
    async def test_cooldown_allows_after_expiry(self):
        """Submission after cooldown expires should be allowed."""
        mock_db = AsyncMock()
        mock_requirement = _make_mock_requirement()

        # Last submission was 2 hours ago (cooldown expired)
        last_submission = datetime.now(UTC) - timedelta(hours=2)

        with (
            patch(
                "services.submissions_service.get_requirement_by_id",
                return_value=mock_requirement,
            ),
            patch(
                "services.submissions_service.SubmissionRepository"
            ) as mock_repo_class,
            patch("services.submissions_service.get_settings") as mock_settings,
            patch(
                "services.submissions_service.validate_submission",
                new_callable=AsyncMock,
            ) as mock_validate,
        ):
            mock_repo = MagicMock()
            mock_repo.get_last_submission_time = AsyncMock(return_value=last_submission)
            mock_repo.upsert = AsyncMock(
                return_value=MagicMock(
                    id=1,
                    requirement_id="test-requirement",
                    submission_type=SubmissionType.CODE_ANALYSIS,
                    phase_id=3,
                    submitted_value="https://github.com/user/repo",
                    extracted_username="user",
                    is_validated=True,
                    validated_at=datetime.now(UTC),
                    verification_completed=True,
                    created_at=datetime.now(UTC),
                )
            )
            mock_repo_class.return_value = mock_repo

            mock_settings.return_value.code_analysis_cooldown_seconds = 3600
            mock_settings.return_value.submission_cooldown_seconds = 3600

            mock_validate.return_value = ValidationResult(
                is_valid=True,
                message="All tasks passed",
            )

            # Should not raise - cooldown expired
            result = await submit_validation(
                db=mock_db,
                user_id="user-123",
                requirement_id="test-requirement",
                submitted_value="https://github.com/user/repo",
                github_username="user",
            )

            assert result.is_valid is True
            mock_validate.assert_called_once()

    @pytest.mark.asyncio
    async def test_server_error_does_not_start_cooldown(self):
        """Server errors should not count toward cooldown.

        If validation fails due to server error (e.g., AI service down),
        the user should be able to retry immediately.
        """
        mock_db = AsyncMock()
        mock_requirement = _make_mock_requirement()

        with (
            patch(
                "services.submissions_service.get_requirement_by_id",
                return_value=mock_requirement,
            ),
            patch(
                "services.submissions_service.SubmissionRepository"
            ) as mock_repo_class,
            patch(
                "services.submissions_service.validate_submission",
                new_callable=AsyncMock,
            ) as mock_validate,
        ):
            mock_repo = MagicMock()
            # No prior submission
            mock_repo.get_last_submission_time = AsyncMock(return_value=None)
            mock_repo.upsert = AsyncMock(
                return_value=MagicMock(
                    id=1,
                    requirement_id="test-requirement",
                    submission_type=SubmissionType.CODE_ANALYSIS,
                    phase_id=3,
                    submitted_value="https://github.com/user/repo",
                    extracted_username="user",
                    is_validated=False,
                    validated_at=None,
                    verification_completed=False,  # Server error!
                    created_at=datetime.now(UTC),
                )
            )
            mock_repo_class.return_value = mock_repo

            # Simulate server error
            mock_validate.return_value = ValidationResult(
                is_valid=False,
                message="Code analysis service unavailable",
                server_error=True,  # This is the key flag
            )

            await submit_validation(
                db=mock_db,
                user_id="user-123",
                requirement_id="test-requirement",
                submitted_value="https://github.com/user/repo",
                github_username="user",
            )

            # Verify upsert was called with verification_completed=False
            call_kwargs = mock_repo.upsert.call_args.kwargs
            assert call_kwargs["verification_completed"] is False

    @pytest.mark.asyncio
    async def test_cooldown_uses_correct_setting_for_code_analysis(self):
        """CODE_ANALYSIS should use code_analysis_cooldown_seconds setting."""
        mock_db = AsyncMock()
        mock_requirement = _make_mock_requirement(
            submission_type=SubmissionType.CODE_ANALYSIS
        )

        # Last submission was 30 minutes ago
        last_submission = datetime.now(UTC) - timedelta(minutes=30)

        with (
            patch(
                "services.submissions_service.get_requirement_by_id",
                return_value=mock_requirement,
            ),
            patch(
                "services.submissions_service.SubmissionRepository"
            ) as mock_repo_class,
            patch("services.submissions_service.get_settings") as mock_settings,
        ):
            mock_repo = MagicMock()
            mock_repo.get_last_submission_time = AsyncMock(return_value=last_submission)
            mock_repo_class.return_value = mock_repo

            # Different cooldowns for different types
            mock_settings.return_value.code_analysis_cooldown_seconds = 7200  # 2 hours
            mock_settings.return_value.submission_cooldown_seconds = 1800  # 30 min

            with pytest.raises(CooldownActiveError) as exc_info:
                await submit_validation(
                    db=mock_db,
                    user_id="user-123",
                    requirement_id="test-requirement",
                    submitted_value="https://github.com/user/repo",
                    github_username="user",
                )

            # Should use code_analysis_cooldown (2 hrs), so ~90 min remaining
            assert exc_info.value.retry_after_seconds > 5000  # More than 83 min

    @pytest.mark.asyncio
    async def test_cooldown_uses_correct_setting_for_other_types(self):
        """Non-CODE_ANALYSIS types should use submission_cooldown_seconds."""
        mock_db = AsyncMock()
        mock_requirement = _make_mock_requirement(
            submission_type=SubmissionType.REPO_FORK
        )

        # Last submission was 20 minutes ago
        last_submission = datetime.now(UTC) - timedelta(minutes=20)

        with (
            patch(
                "services.submissions_service.get_requirement_by_id",
                return_value=mock_requirement,
            ),
            patch(
                "services.submissions_service.SubmissionRepository"
            ) as mock_repo_class,
            patch("services.submissions_service.get_settings") as mock_settings,
        ):
            mock_repo = MagicMock()
            mock_repo.get_last_submission_time = AsyncMock(return_value=last_submission)
            mock_repo_class.return_value = mock_repo

            # Different cooldowns
            mock_settings.return_value.code_analysis_cooldown_seconds = 7200  # 2 hours
            mock_settings.return_value.submission_cooldown_seconds = 1800  # 30 min

            with pytest.raises(CooldownActiveError) as exc_info:
                await submit_validation(
                    db=mock_db,
                    user_id="user-123",
                    requirement_id="test-requirement",
                    submitted_value="https://github.com/user/repo",
                    github_username="user",
                )

            # Should use submission_cooldown (30 min), so ~10 min remaining
            assert exc_info.value.retry_after_seconds < 700  # Less than 11.6 min
            assert exc_info.value.retry_after_seconds > 500  # More than 8.3 min


@pytest.mark.unit
class TestSubmissionValidationErrors:
    """Tests for error handling in submit_validation."""

    @pytest.mark.asyncio
    async def test_requirement_not_found_raises_error(self):
        """Unknown requirement ID should raise RequirementNotFoundError."""
        mock_db = AsyncMock()

        with patch(
            "services.submissions_service.get_requirement_by_id",
            return_value=None,
        ):
            with pytest.raises(RequirementNotFoundError):
                await submit_validation(
                    db=mock_db,
                    user_id="user-123",
                    requirement_id="nonexistent",
                    submitted_value="https://github.com/user/repo",
                    github_username="user",
                )

    @pytest.mark.asyncio
    async def test_github_username_required_for_code_analysis(self):
        """CODE_ANALYSIS without github_username should raise error."""
        mock_db = AsyncMock()
        mock_requirement = _make_mock_requirement(
            submission_type=SubmissionType.CODE_ANALYSIS
        )

        with (
            patch(
                "services.submissions_service.get_requirement_by_id",
                return_value=mock_requirement,
            ),
            patch(
                "services.submissions_service.SubmissionRepository"
            ) as mock_repo_class,
        ):
            mock_repo = MagicMock()
            mock_repo.get_last_submission_time = AsyncMock(return_value=None)
            mock_repo_class.return_value = mock_repo

            with pytest.raises(GitHubUsernameRequiredError):
                await submit_validation(
                    db=mock_db,
                    user_id="user-123",
                    requirement_id="test-requirement",
                    submitted_value="https://github.com/user/repo",
                    github_username=None,  # Missing!
                )


@pytest.mark.unit
class TestConcurrentSubmissionProtection:
    """Tests for concurrent submission lock protection."""

    @pytest.mark.asyncio
    async def test_lock_is_per_user_requirement(self):
        """Different user+requirement combinations should have separate locks."""
        lock1 = await _get_submission_lock("user-1", "req-1")
        lock2 = await _get_submission_lock("user-1", "req-2")
        lock3 = await _get_submission_lock("user-2", "req-1")

        # All should be different lock instances
        assert lock1 is not lock2
        assert lock1 is not lock3
        assert lock2 is not lock3

    @pytest.mark.asyncio
    async def test_same_user_requirement_gets_same_lock(self):
        """Same user+requirement should return the same lock instance."""
        lock1 = await _get_submission_lock("user-1", "req-1")
        lock2 = await _get_submission_lock("user-1", "req-1")

        assert lock1 is lock2

    @pytest.mark.asyncio
    async def test_concurrent_submission_raises_error(self):
        """Second submission while first is in progress should raise error."""
        mock_db = AsyncMock()
        mock_requirement = _make_mock_requirement()

        # Pre-acquire the lock to simulate in-progress submission
        lock = await _get_submission_lock("user-123", "test-requirement")

        with (
            patch(
                "services.submissions_service.get_requirement_by_id",
                return_value=mock_requirement,
            ),
            patch(
                "services.submissions_service.SubmissionRepository"
            ) as mock_repo_class,
        ):
            mock_repo = MagicMock()
            mock_repo.get_last_submission_time = AsyncMock(return_value=None)
            mock_repo_class.return_value = mock_repo

            # Acquire the lock (simulating first request in progress)
            async with lock:
                # Second request should fail immediately
                with pytest.raises(ConcurrentSubmissionError) as exc_info:
                    await submit_validation(
                        db=mock_db,
                        user_id="user-123",
                        requirement_id="test-requirement",
                        submitted_value="https://github.com/user/repo",
                        github_username="user",
                    )

                assert "already in progress" in str(exc_info.value)
