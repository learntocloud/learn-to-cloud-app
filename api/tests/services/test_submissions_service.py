"""Tests for submissions_service abuse protection.

Tests cover:
- Daily submission cap enforcement
- Already-validated short-circuit
- Concurrent submission protection
- Sequential phase gating
"""

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from models import SubmissionType
from schemas import HandsOnRequirement, ValidationResult
from services.submissions_service import (
    AlreadyValidatedError,
    ConcurrentSubmissionError,
    DailyLimitExceededError,
    GitHubUsernameRequiredError,
    PriorPhaseNotCompleteError,
    RequirementNotFoundError,
    _get_submission_lock,
    get_phase_submission_context,
    submit_validation,
)


@pytest.fixture(autouse=True)
def _mock_phase_id_mapping():
    """Mock requirement → phase mapping and prerequisite functions for all tests."""
    with (
        patch(
            "services.submissions_service.get_phase_id_for_requirement",
            autospec=True,
            return_value=3,
        ),
        patch(
            "services.submissions_service.get_prerequisite_phase",
            autospec=True,
            return_value=None,
        ),
        patch(
            "services.submissions_service.get_requirement_ids_for_phase",
            autospec=True,
            return_value=[],
        ),
    ):
        yield


def _make_mock_requirement(
    submission_type: SubmissionType = SubmissionType.CI_STATUS,
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
    submission_type: SubmissionType = SubmissionType.CI_STATUS,
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
class TestSubmissionValidationErrors:
    """Tests for error handling in submit_validation."""

    @pytest.mark.asyncio
    async def test_requirement_not_found_raises_error(self):
        """Unknown requirement ID should raise RequirementNotFoundError."""
        mock_session_maker = _mock_session_maker()

        with (
            patch(
                "services.submissions_service.get_requirement_by_id",
                autospec=True,
                return_value=None,
            ),
            pytest.raises(RequirementNotFoundError),
        ):
            await submit_validation(
                session_maker=mock_session_maker,
                user_id=123,
                requirement_id="nonexistent",
                submitted_value="https://github.com/user/repo",
                github_username="user",
            )

    @pytest.mark.asyncio
    async def test_github_username_required_for_ci_status(self):
        """CI_STATUS without github_username should raise error."""
        mock_session_maker = _mock_session_maker()
        mock_requirement = _make_mock_requirement(
            submission_type=SubmissionType.CI_STATUS
        )

        with (
            patch(
                "services.submissions_service.get_requirement_by_id",
                autospec=True,
                return_value=mock_requirement,
            ),
            patch(
                "services.submissions_service.SubmissionRepository",
                autospec=True,
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
                autospec=True,
                return_value=mock_requirement,
            ),
            patch(
                "services.submissions_service.SubmissionRepository",
                autospec=True,
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
                autospec=True,
                return_value=mock_requirement,
            ),
            patch(
                "services.submissions_service.SubmissionRepository",
                autospec=True,
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
                autospec=True,
                return_value=mock_requirement,
            ),
            patch(
                "services.submissions_service.SubmissionRepository",
                autospec=True,
            ) as mock_repo_class,
            patch(
                "services.submissions_service.validate_submission",
                autospec=True,
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
                    submission_type=SubmissionType.CI_STATUS,
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
                autospec=True,
                return_value=mock_requirement,
            ),
            patch(
                "services.submissions_service.SubmissionRepository",
                autospec=True,
            ) as mock_repo_class,
            patch(
                "services.submissions_service.get_settings", autospec=True
            ) as mock_settings,
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
                autospec=True,
                return_value=mock_requirement,
            ),
            patch(
                "services.submissions_service.SubmissionRepository",
                autospec=True,
            ) as mock_repo_class,
            patch(
                "services.submissions_service.get_settings", autospec=True
            ) as mock_settings,
            patch(
                "services.submissions_service.validate_submission",
                autospec=True,
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
                    submission_type=SubmissionType.CI_STATUS,
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
class TestSequentialPhaseGating:
    """Tests for sequential phase verification gating."""

    @pytest.mark.asyncio
    async def test_submission_blocked_when_prior_phase_incomplete(self):
        """Submission should raise PriorPhaseNotCompleteError
        when prerequisite phase is incomplete."""
        mock_session_maker = _mock_session_maker()
        mock_requirement = _make_mock_requirement(
            submission_type=SubmissionType.DEPLOYED_API,
        )

        with (
            patch(
                "services.submissions_service.get_requirement_by_id",
                autospec=True,
                return_value=mock_requirement,
            ),
            patch(
                "services.submissions_service.get_phase_id_for_requirement",
                return_value=4,  # no autospec: autouse fixture
            ),
            patch(
                "services.submissions_service.get_prerequisite_phase",
                return_value=3,  # no autospec: autouse fixture
            ),
            patch(
                "services.submissions_service.get_requirement_ids_for_phase",
                return_value=[
                    "journal-pr-logging",
                    "journal-pr-get-entry",
                ],  # no autospec: autouse fixture
            ),
            patch(
                "services.submissions_service.SubmissionRepository",
                autospec=True,
            ) as mock_repo_class,
        ):
            mock_repo = MagicMock()
            mock_repo.get_by_user_and_requirement = AsyncMock(return_value=None)
            mock_repo.count_submissions_today = AsyncMock(return_value=0)
            mock_repo.are_all_requirements_validated = AsyncMock(return_value=False)
            mock_repo_class.return_value = mock_repo

            with pytest.raises(PriorPhaseNotCompleteError) as exc_info:
                await submit_validation(
                    session_maker=mock_session_maker,
                    user_id=123,
                    requirement_id="deployed-journal-api",
                    submitted_value="https://api.example.com",
                    github_username="user",
                )

            assert exc_info.value.prerequisite_phase == 3
            assert "Phase 3" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_submission_allowed_when_prior_phase_complete(self):
        """Submission should proceed when prerequisite phase is fully verified."""
        mock_session_maker = _mock_session_maker()
        mock_requirement = _make_mock_requirement(
            submission_type=SubmissionType.DEPLOYED_API,
        )

        with (
            patch(
                "services.submissions_service.get_requirement_by_id",
                autospec=True,
                return_value=mock_requirement,
            ),
            patch(
                "services.submissions_service.get_phase_id_for_requirement",
                return_value=4,  # no autospec: autouse fixture
            ),
            patch(
                "services.submissions_service.get_prerequisite_phase",
                return_value=3,  # no autospec: autouse fixture
            ),
            patch(
                "services.submissions_service.get_requirement_ids_for_phase",
                return_value=["journal-pr-logging"],  # no autospec: autouse fixture
            ),
            patch(
                "services.submissions_service.SubmissionRepository",
                autospec=True,
            ) as mock_repo_class,
            patch(
                "services.submissions_service.validate_submission",
                autospec=True,
            ) as mock_validate,
        ):
            mock_repo = MagicMock()
            mock_repo.get_by_user_and_requirement = AsyncMock(return_value=None)
            mock_repo.count_submissions_today = AsyncMock(return_value=0)
            mock_repo.get_last_submission_time = AsyncMock(return_value=None)
            mock_repo.are_all_requirements_validated = AsyncMock(return_value=True)
            mock_repo.create = AsyncMock(
                return_value=MagicMock(
                    id=1,
                    requirement_id="deployed-journal-api",
                    submission_type=SubmissionType.DEPLOYED_API,
                    phase_id=4,
                    submitted_value="https://api.example.com",
                    extracted_username=None,
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
                message="Deployed API verified!",
            )

            result = await submit_validation(
                session_maker=mock_session_maker,
                user_id=123,
                requirement_id="deployed-journal-api",
                submitted_value="https://api.example.com",
                github_username="user",
            )

            assert result.is_valid is True
            mock_validate.assert_called_once()


# ---------------------------------------------------------------------------
# get_phase_submission_context
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetPhaseSubmissionContext:
    @pytest.mark.asyncio
    async def test_empty_submissions(self):
        with patch(
            "services.submissions_service.SubmissionRepository", autospec=True
        ) as MockRepo:
            MockRepo.return_value.get_by_user_and_phase = AsyncMock(return_value=[])
            result = await get_phase_submission_context(
                AsyncMock(), user_id=1, phase_id=3
            )
        assert result.submissions_by_req == {}
        assert result.feedback_by_req == {}

    @pytest.mark.asyncio
    async def test_submission_without_feedback(self):
        mock_sub = _make_mock_submission(is_validated=True)
        mock_sub.feedback_json = None
        with patch(
            "services.submissions_service.SubmissionRepository", autospec=True
        ) as MockRepo:
            MockRepo.return_value.get_by_user_and_phase = AsyncMock(
                return_value=[mock_sub]
            )
            result = await get_phase_submission_context(
                AsyncMock(), user_id=1, phase_id=3
            )
        assert "test-requirement" in result.submissions_by_req
        assert result.feedback_by_req == {}

    @pytest.mark.asyncio
    async def test_submission_with_feedback_json(self):
        mock_sub = _make_mock_submission(
            is_validated=False, verification_completed=True
        )
        mock_sub.feedback_json = '[{"task_name":"A","passed":true,"feedback":"ok"}]'
        with (
            patch(
                "services.submissions_service.SubmissionRepository", autospec=True
            ) as MockRepo,
        ):
            MockRepo.return_value.get_by_user_and_phase = AsyncMock(
                return_value=[mock_sub]
            )
            result = await get_phase_submission_context(
                AsyncMock(), user_id=1, phase_id=3
            )
        assert "test-requirement" in result.feedback_by_req
        feedback = result.feedback_by_req["test-requirement"]
        assert feedback["passed"] == 1
