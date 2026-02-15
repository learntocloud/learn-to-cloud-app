"""Tests for submissions_service abuse protection.

Tests cover:
- Cooldown is enforced for CODE_ANALYSIS submissions
- Cooldown is enforced for other submission types
- Server errors exempt from cooldown (verification_completed=False)
- First submission always allowed (no prior record)
- Cooldown respects configured duration
- Daily submission cap enforcement
- Already-validated short-circuit
"""

from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from models import SubmissionType
from schemas import HandsOnRequirement, ValidationResult
from services.submissions_service import (
    AlreadyValidatedError,
    ConcurrentSubmissionError,
    CooldownActiveError,
    DailyLimitExceededError,
    GitHubUsernameRequiredError,
    RequirementNotFoundError,
    _get_submission_lock,
    submit_validation,
)


@pytest.fixture(autouse=True)
def _mock_phase_id_mapping():
    """Mock requirement → phase mapping for all tests in this module."""
    with patch(
        "services.submissions_service.get_phase_id_for_requirement", return_value=3
    ):
        yield


def _make_mock_requirement(
    submission_type: SubmissionType = SubmissionType.CODE_ANALYSIS,
) -> HandsOnRequirement:
    """Create a mock requirement for testing."""
    return HandsOnRequirement(
        id="test-requirement",
        submission_type=submission_type,
        name="Test Requirement",
        description="Test description",
    )


def _make_mock_submission(
    *,
    is_validated: bool = False,
    verification_completed: bool = True,
    submission_type: SubmissionType = SubmissionType.CODE_ANALYSIS,
) -> MagicMock:
    """Create a mock Submission DB model with all fields for _to_submission_data."""
    return MagicMock(
        id=1,
        requirement_id="test-requirement",
        submission_type=submission_type,
        phase_id=3,
        submitted_value="https://github.com/user/repo",
        extracted_username="user",
        is_validated=is_validated,
        validated_at=datetime.now(UTC) if is_validated else None,
        verification_completed=verification_completed,
        feedback_json=None,
        validation_message=None,
        cloud_provider=None,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


def _mock_session_maker():
    """Create a mock async_sessionmaker for testing.

    Returns a callable that produces async context managers yielding
    an AsyncMock session.  Since tests patch SubmissionRepository,
    the actual session object is irrelevant — it just needs to support
    the async-with protocol and have a .commit() coroutine.
    """

    @asynccontextmanager
    async def _factory():
        yield AsyncMock()

    return _factory


@pytest.mark.unit
class TestCooldownEnforcement:
    """Tests for cooldown logic in submit_validation."""

    @pytest.mark.asyncio
    async def test_first_submission_allowed(self):
        """First submission should always be allowed (no cooldown)."""
        mock_session_maker = _mock_session_maker()
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
            mock_repo.get_by_user_and_requirement = AsyncMock(return_value=None)
            mock_repo.count_submissions_today = AsyncMock(return_value=0)
            mock_repo.get_last_submission_time = AsyncMock(return_value=None)
            mock_repo.create = AsyncMock(
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
                    feedback_json=None,
                    validation_message=None,
                    cloud_provider=None,
                    updated_at=datetime.now(UTC),
                )
            )
            mock_repo_class.return_value = mock_repo

            mock_validate.return_value = ValidationResult(
                is_valid=True,
                message="All tasks passed",
            )

            result = await submit_validation(
                session_maker=mock_session_maker,
                user_id=123,
                requirement_id="test-requirement",
                submitted_value="https://github.com/user/repo",
                github_username="user",
            )

            assert result.is_valid is True
            mock_validate.assert_called_once()

    @pytest.mark.asyncio
    async def test_cooldown_blocks_rapid_resubmission(self):
        """Submission within cooldown period should raise CooldownActiveError."""
        mock_session_maker = _mock_session_maker()
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
            mock_repo.get_by_user_and_requirement = AsyncMock(
                return_value=MagicMock(
                    id=1,
                    requirement_id="test-requirement",
                    submission_type=SubmissionType.CODE_ANALYSIS,
                    phase_id=3,
                    submitted_value="https://github.com/user/repo",
                    extracted_username="user",
                    is_validated=False,
                    validated_at=None,
                    verification_completed=True,
                    feedback_json=None,
                    validation_message=None,
                    cloud_provider=None,
                    created_at=datetime.now(UTC),
                    updated_at=datetime.now(UTC),
                )
            )
            mock_repo.count_submissions_today = AsyncMock(return_value=0)
            mock_repo.get_last_submission_time = AsyncMock(return_value=last_submission)
            mock_repo_class.return_value = mock_repo

            mock_settings.return_value.code_analysis_cooldown_seconds = 3600
            mock_settings.return_value.daily_submission_limit = 20

            with pytest.raises(CooldownActiveError) as exc_info:
                await submit_validation(
                    session_maker=mock_session_maker,
                    user_id=123,
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
        mock_session_maker = _mock_session_maker()
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
            mock_repo.get_by_user_and_requirement = AsyncMock(
                return_value=_make_mock_submission()
            )
            mock_repo.count_submissions_today = AsyncMock(return_value=0)
            mock_repo.get_last_submission_time = AsyncMock(return_value=last_submission)
            mock_repo.create = AsyncMock(
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
                    feedback_json=None,
                    validation_message=None,
                    cloud_provider=None,
                    updated_at=datetime.now(UTC),
                )
            )
            mock_repo_class.return_value = mock_repo

            mock_settings.return_value.code_analysis_cooldown_seconds = 3600
            mock_settings.return_value.daily_submission_limit = 20

            mock_validate.return_value = ValidationResult(
                is_valid=True,
                message="All tasks passed",
            )

            result = await submit_validation(
                session_maker=mock_session_maker,
                user_id=123,
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
        mock_session_maker = _mock_session_maker()
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
            mock_repo.get_by_user_and_requirement = AsyncMock(return_value=None)
            mock_repo.count_submissions_today = AsyncMock(return_value=0)
            mock_repo.get_last_submission_time = AsyncMock(return_value=None)
            mock_repo.create = AsyncMock(
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
                    feedback_json=None,
                    validation_message=None,
                    cloud_provider=None,
                    updated_at=datetime.now(UTC),
                )
            )
            mock_repo_class.return_value = mock_repo

            mock_validate.return_value = ValidationResult(
                is_valid=False,
                message="Code analysis service unavailable",
                server_error=True,  # This is the key flag
            )

            await submit_validation(
                session_maker=mock_session_maker,
                user_id=123,
                requirement_id="test-requirement",
                submitted_value="https://github.com/user/repo",
                github_username="user",
            )

            call_kwargs = mock_repo.create.call_args.kwargs
            assert call_kwargs["verification_completed"] is False

    @pytest.mark.asyncio
    async def test_immediate_retry_allowed_after_server_error(self):
        """User should be able to retry immediately after a server error.

        Regression test: when the LLM service is misconfigured (e.g. wrong
        env var name), the first attempt fails with server_error=True. The
        second attempt should NOT be blocked by cooldown because server
        errors set verification_completed=False — and the cooldown query
        filters by verification_completed=True.
        """
        mock_session_maker = _mock_session_maker()
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
            mock_repo.count_submissions_today = AsyncMock(return_value=1)

            # --- First submission: server error ---
            mock_repo.get_by_user_and_requirement = AsyncMock(return_value=None)
            mock_repo.get_last_submission_time = AsyncMock(return_value=None)
            mock_repo.create = AsyncMock(
                return_value=MagicMock(
                    id=1,
                    requirement_id="test-requirement",
                    submission_type=SubmissionType.CODE_ANALYSIS,
                    phase_id=3,
                    submitted_value="https://github.com/user/repo",
                    extracted_username="user",
                    is_validated=False,
                    validated_at=None,
                    verification_completed=False,
                    created_at=datetime.now(UTC),
                    feedback_json=None,
                    validation_message=None,
                    cloud_provider=None,
                    updated_at=datetime.now(UTC),
                )
            )
            mock_repo_class.return_value = mock_repo

            mock_validate.return_value = ValidationResult(
                is_valid=False,
                message="Unable to connect to code analysis service.",
                server_error=True,
            )

            result1 = await submit_validation(
                session_maker=mock_session_maker,
                user_id=456,
                requirement_id="test-requirement",
                submitted_value="https://github.com/user/repo",
                github_username="user",
            )
            assert result1.is_valid is False

            # --- Second submission (immediate retry): should NOT be blocked ---
            mock_repo.get_by_user_and_requirement = AsyncMock(
                return_value=_make_mock_submission()
            )
            mock_repo.get_last_submission_time = AsyncMock(return_value=None)
            mock_repo.create = AsyncMock(
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
                    feedback_json=None,
                    validation_message=None,
                    cloud_provider=None,
                    updated_at=datetime.now(UTC),
                )
            )

            mock_validate.return_value = ValidationResult(
                is_valid=True,
                message="All tasks passed",
            )

            result2 = await submit_validation(
                session_maker=mock_session_maker,
                user_id=456,
                requirement_id="test-requirement",
                submitted_value="https://github.com/user/repo",
                github_username="user",
            )
            assert result2.is_valid is True

    @pytest.mark.asyncio
    async def test_cooldown_uses_correct_setting_for_code_analysis(self):
        """CODE_ANALYSIS should use code_analysis_cooldown_seconds setting."""
        mock_session_maker = _mock_session_maker()
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
            mock_repo.get_by_user_and_requirement = AsyncMock(
                return_value=MagicMock(
                    id=1,
                    requirement_id="test-requirement",
                    submission_type=SubmissionType.CODE_ANALYSIS,
                    phase_id=3,
                    submitted_value="https://github.com/user/repo",
                    extracted_username="user",
                    is_validated=False,
                    validated_at=None,
                    verification_completed=True,
                    feedback_json=None,
                    validation_message=None,
                    cloud_provider=None,
                    created_at=datetime.now(UTC),
                    updated_at=datetime.now(UTC),
                )
            )
            mock_repo.count_submissions_today = AsyncMock(return_value=0)
            mock_repo.get_last_submission_time = AsyncMock(return_value=last_submission)
            mock_repo_class.return_value = mock_repo

            mock_settings.return_value.code_analysis_cooldown_seconds = 7200  # 2 hours
            mock_settings.return_value.daily_submission_limit = 20

            with pytest.raises(CooldownActiveError) as exc_info:
                await submit_validation(
                    session_maker=mock_session_maker,
                    user_id=123,
                    requirement_id="test-requirement",
                    submitted_value="https://github.com/user/repo",
                    github_username="user",
                )

            # Should use code_analysis_cooldown (2 hrs), so ~90 min remaining
            assert exc_info.value.retry_after_seconds > 5000  # More than 83 min

    @pytest.mark.asyncio
    async def test_no_cooldown_for_lightweight_types(self):
        """Non-LLM types (e.g. REPO_FORK) should have no cooldown."""
        mock_session_maker = _mock_session_maker()
        mock_requirement = _make_mock_requirement(
            submission_type=SubmissionType.REPO_FORK
        )

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
            mock_repo.get_by_user_and_requirement = AsyncMock(
                return_value=_make_mock_submission()
            )
            mock_repo.count_submissions_today = AsyncMock(return_value=0)
            # get_last_submission_time should NOT be called for lightweight types
            mock_repo.get_last_submission_time = AsyncMock(return_value=None)
            mock_repo.create = AsyncMock(
                return_value=MagicMock(
                    id=1,
                    requirement_id="test-requirement",
                    submission_type=SubmissionType.REPO_FORK,
                    phase_id=3,
                    submitted_value="https://github.com/user/repo",
                    extracted_username="user",
                    is_validated=True,
                    validated_at=datetime.now(UTC),
                    verification_completed=True,
                    created_at=datetime.now(UTC),
                    feedback_json=None,
                    validation_message=None,
                    cloud_provider=None,
                    updated_at=datetime.now(UTC),
                )
            )
            mock_repo_class.return_value = mock_repo

            mock_settings.return_value.code_analysis_cooldown_seconds = 3600
            mock_settings.return_value.daily_submission_limit = 20

            mock_validate.return_value = ValidationResult(
                is_valid=True,
                message="Verified",
            )

            result = await submit_validation(
                session_maker=mock_session_maker,
                user_id=123,
                requirement_id="test-requirement",
                submitted_value="https://github.com/user/repo",
                github_username="user",
            )
            assert result.is_valid is True

            mock_repo.get_last_submission_time.assert_not_called()


@pytest.mark.unit
class TestSubmissionValidationErrors:
    """Tests for error handling in submit_validation."""

    @pytest.mark.asyncio
    async def test_requirement_not_found_raises_error(self):
        """Unknown requirement ID should raise RequirementNotFoundError."""
        mock_session_maker = _mock_session_maker()

        with patch(
            "services.submissions_service.get_requirement_by_id",
            return_value=None,
        ):
            with pytest.raises(RequirementNotFoundError):
                await submit_validation(
                    session_maker=mock_session_maker,
                    user_id=123,
                    requirement_id="nonexistent",
                    submitted_value="https://github.com/user/repo",
                    github_username="user",
                )

    @pytest.mark.asyncio
    async def test_github_username_required_for_code_analysis(self):
        """CODE_ANALYSIS without github_username should raise error."""
        mock_session_maker = _mock_session_maker()
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
            mock_repo.get_by_user_and_requirement = AsyncMock(return_value=None)
            mock_repo.count_submissions_today = AsyncMock(return_value=0)
            mock_repo.get_last_submission_time = AsyncMock(return_value=None)
            mock_repo_class.return_value = mock_repo

            with pytest.raises(GitHubUsernameRequiredError):
                await submit_validation(
                    session_maker=mock_session_maker,
                    user_id=123,
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
        lock1 = await _get_submission_lock(1, "req-1")
        lock2 = await _get_submission_lock(1, "req-2")
        lock3 = await _get_submission_lock(2, "req-1")

        # All should be different lock instances
        assert lock1 is not lock2
        assert lock1 is not lock3
        assert lock2 is not lock3

    @pytest.mark.asyncio
    async def test_same_user_requirement_gets_same_lock(self):
        """Same user+requirement should return the same lock instance."""
        lock1 = await _get_submission_lock(1, "req-1")
        lock2 = await _get_submission_lock(1, "req-1")

        assert lock1 is lock2

    @pytest.mark.asyncio
    async def test_concurrent_submission_raises_error(self):
        """Second submission while first is in progress should raise error."""
        mock_session_maker = _mock_session_maker()
        mock_requirement = _make_mock_requirement()

        # Pre-acquire the lock to simulate in-progress submission
        lock = await _get_submission_lock(123, "test-requirement")

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
            mock_repo.get_by_user_and_requirement = AsyncMock(return_value=None)
            mock_repo.count_submissions_today = AsyncMock(return_value=0)
            mock_repo.get_last_submission_time = AsyncMock(return_value=None)
            mock_repo_class.return_value = mock_repo

            # Acquire the lock (simulating first request in progress)
            async with lock:
                # Second request should fail immediately
                with pytest.raises(ConcurrentSubmissionError) as exc_info:
                    await submit_validation(
                        session_maker=mock_session_maker,
                        user_id=123,
                        requirement_id="test-requirement",
                        submitted_value="https://github.com/user/repo",
                        github_username="user",
                    )

                assert "already in progress" in str(exc_info.value)


@pytest.mark.unit
class TestAlreadyValidatedShortCircuit:
    """Tests for already-validated requirement short-circuit."""

    @pytest.mark.asyncio
    async def test_already_validated_raises_error(self):
        """Re-submitting a validated requirement should raise AlreadyValidatedError."""
        mock_session_maker = _mock_session_maker()
        mock_requirement = _make_mock_requirement()

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
            # Existing submission is already validated
            mock_repo.get_by_user_and_requirement = AsyncMock(
                return_value=MagicMock(is_validated=True)
            )
            mock_repo_class.return_value = mock_repo

            with pytest.raises(AlreadyValidatedError):
                await submit_validation(
                    session_maker=mock_session_maker,
                    user_id=123,
                    requirement_id="test-requirement",
                    submitted_value="https://github.com/user/repo",
                    github_username="user",
                )

    @pytest.mark.asyncio
    async def test_failed_submission_allows_retry(self):
        """A previously failed (not validated) submission should allow retry."""
        mock_session_maker = _mock_session_maker()
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
            # Existing submission is NOT validated — retry allowed
            mock_repo.get_by_user_and_requirement = AsyncMock(
                return_value=_make_mock_submission()
            )
            mock_repo.count_submissions_today = AsyncMock(return_value=0)
            mock_repo.get_last_submission_time = AsyncMock(return_value=None)
            mock_repo.create = AsyncMock(
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
                    feedback_json=None,
                    validation_message=None,
                    cloud_provider=None,
                    updated_at=datetime.now(UTC),
                )
            )
            mock_repo_class.return_value = mock_repo

            mock_validate.return_value = ValidationResult(
                is_valid=True,
                message="All tasks passed",
            )

            result = await submit_validation(
                session_maker=mock_session_maker,
                user_id=123,
                requirement_id="test-requirement",
                submitted_value="https://github.com/user/repo",
                github_username="user",
            )

            assert result.is_valid is True


@pytest.mark.unit
class TestDailySubmissionCap:
    """Tests for global daily submission limit."""

    @pytest.mark.asyncio
    async def test_daily_limit_exceeded_raises_error(self):
        """Exceeding daily submission cap should raise DailyLimitExceededError."""
        mock_session_maker = _mock_session_maker()
        mock_requirement = _make_mock_requirement()

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
            mock_repo.get_by_user_and_requirement = AsyncMock(return_value=None)
            mock_repo.count_submissions_today = AsyncMock(return_value=20)
            mock_repo_class.return_value = mock_repo

            mock_settings.return_value.daily_submission_limit = 20

            with pytest.raises(DailyLimitExceededError) as exc_info:
                await submit_validation(
                    session_maker=mock_session_maker,
                    user_id=123,
                    requirement_id="test-requirement",
                    submitted_value="https://github.com/user/repo",
                    github_username="user",
                )

            assert exc_info.value.limit == 20

    @pytest.mark.asyncio
    async def test_under_daily_limit_allowed(self):
        """Submissions under the daily cap should proceed normally."""
        mock_session_maker = _mock_session_maker()
        mock_requirement = _make_mock_requirement()

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
            mock_repo.get_by_user_and_requirement = AsyncMock(return_value=None)
            mock_repo.count_submissions_today = AsyncMock(return_value=5)
            mock_repo.get_last_submission_time = AsyncMock(return_value=None)
            mock_repo.create = AsyncMock(
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
                    feedback_json=None,
                    validation_message=None,
                    cloud_provider=None,
                    updated_at=datetime.now(UTC),
                )
            )
            mock_repo_class.return_value = mock_repo

            mock_settings.return_value.daily_submission_limit = 20
            mock_settings.return_value.code_analysis_cooldown_seconds = 3600

            mock_validate.return_value = ValidationResult(
                is_valid=True,
                message="All tasks passed",
            )

            result = await submit_validation(
                session_maker=mock_session_maker,
                user_id=123,
                requirement_id="test-requirement",
                submitted_value="https://github.com/user/repo",
                github_username="user",
            )

            assert result.is_valid is True
