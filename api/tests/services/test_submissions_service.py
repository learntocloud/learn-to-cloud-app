"""Tests for submissions_service verification job pre-validation.

Tests cover:
- Already-validated short-circuit
- Sequential phase gating
"""

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from learn_to_cloud_shared.models import SubmissionType, SubmissionValueKind
from learn_to_cloud_shared.requirements import RequirementIndex
from learn_to_cloud_shared.schemas import HandsOnRequirement, Phase

from learn_to_cloud.services.submissions_service import (
    _SMOKE_USER_ID as SMOKE_USER_ID,
)
from learn_to_cloud.services.submissions_service import (
    AlreadyValidatedError,
    PriorPhaseNotCompleteError,
    RequirementNotFoundError,
    VerificationJobSubmission,
    create_verification_job,
    get_phase_submission_context,
    run_submit_smoke_check,
)
from learn_to_cloud.services.submissions_service import (
    _pick_smoke_requirement as pick_smoke_requirement,
)


def _make_mock_requirement(
    submission_type: SubmissionType = SubmissionType.JOURNAL_API_VERIFIER,
) -> HandsOnRequirement:
    """Create a mock requirement for testing."""
    from learn_to_cloud_shared.testing.requirement_factories import make_requirement

    return make_requirement(
        submission_type,
        slug="test-requirement",
        name="Test Requirement",
        description="Test description",
    )


def _make_mock_submission(
    *,
    is_validated: bool = False,
    verification_completed: bool = True,
    submission_type: SubmissionType = SubmissionType.JOURNAL_API_VERIFIER,
) -> MagicMock:
    """Create a mock Submission DB model with all fields for _to_submission_data."""
    return MagicMock(
        id=1,
        requirement_slug="test-requirement",
        submission_type=submission_type,
        phase_id=3,
        submitted_value="https://github.com/user/repo",
        submission_value_kind=SubmissionValueKind.GITHUB_URL.value,
        github_url="https://github.com/user/repo",
        token_value=None,
        deployed_url=None,
        text_value=None,
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
    an AsyncMock session. Since tests patch SubmissionRepository,
    the actual session object is irrelevant -- it just needs to support
    the async-with protocol and have a .commit() coroutine.
    """

    @asynccontextmanager
    async def _factory():
        yield AsyncMock()

    return _factory


def _build_index(
    requirement: HandsOnRequirement | None,
    *,
    phase_id: int = 3,
    prereq_phase: int | None = None,
    prereq_req_ids: list[str] | None = None,
) -> RequirementIndex:
    """Build a RequirementIndex containing the given requirement plus optional
    prerequisite-phase requirement ids.

    The submissions service only ever reads ``by_id``, ``phase_order_by_req_slug``,
    and ``requirement_ids_for_phase`` from the index. We construct the prereq
    requirements with the real factory so the index's type signature stays
    honest.
    """
    from learn_to_cloud_shared.testing.requirement_factories import (
        journal_api_verifier_requirement,
    )

    by_phase: dict[int, list[HandsOnRequirement]] = {}
    by_slug: dict[str, HandsOnRequirement] = {}
    phase_order_by_req_slug: dict[str, int] = {}
    if requirement is not None:
        by_phase[phase_id] = [requirement]
        by_slug[requirement.slug] = requirement
        phase_order_by_req_slug[requirement.slug] = phase_id
    if prereq_phase is not None and prereq_req_ids:
        prereq_reqs = [
            journal_api_verifier_requirement(
                slug=req_id, name="stub", description="stub"
            )
            for req_id in prereq_req_ids
        ]
        by_phase[prereq_phase] = list(prereq_reqs)
        for req in prereq_reqs:
            phase_order_by_req_slug[req.slug] = prereq_phase
    return RequirementIndex(
        by_phase_order=by_phase,
        by_slug=by_slug,
        phase_order_by_req_slug=phase_order_by_req_slug,
    )


@pytest.mark.unit
class TestSubmissionValidationErrors:
    """Tests for error handling in create_verification_job."""

    @pytest.mark.asyncio
    async def test_requirement_not_found_raises_error(self):
        mock_session_maker = _mock_session_maker()

        with (
            patch(
                "learn_to_cloud.services.submissions_service.load_requirement_index",
                new_callable=AsyncMock,
                return_value=_build_index(None),
            ),
            pytest.raises(RequirementNotFoundError),
        ):
            await create_verification_job(
                session_maker=mock_session_maker,
                user_id=123,
                requirement_slug="nonexistent",
                submitted_value="https://github.com/user/repo",
                github_username="user",
            )


@pytest.mark.unit
class TestAlreadyValidatedShortCircuit:
    @pytest.mark.asyncio
    async def test_already_validated_raises_error(self):
        mock_session_maker = _mock_session_maker()
        mock_requirement = _make_mock_requirement()

        with (
            patch(
                "learn_to_cloud.services.submissions_service.load_requirement_index",
                new_callable=AsyncMock,
                return_value=_build_index(mock_requirement),
            ),
            patch(
                "learn_to_cloud.services.submissions_service.SubmissionRepository",
                autospec=True,
            ) as mock_repo_class,
        ):
            mock_repo = MagicMock()
            mock_repo.get_by_user_and_requirement = AsyncMock(
                return_value=MagicMock(is_validated=True)
            )
            mock_repo_class.return_value = mock_repo

            with pytest.raises(AlreadyValidatedError):
                await create_verification_job(
                    session_maker=mock_session_maker,
                    user_id=123,
                    requirement_slug="test-requirement",
                    submitted_value="https://github.com/user/repo",
                    github_username="user",
                )

    @pytest.mark.asyncio
    async def test_failed_submission_allows_retry(self):
        mock_session_maker = _mock_session_maker()
        mock_requirement = _make_mock_requirement()

        with (
            patch(
                "learn_to_cloud.services.submissions_service.load_requirement_index",
                new_callable=AsyncMock,
                return_value=_build_index(mock_requirement),
            ),
            patch(
                "learn_to_cloud.services.submissions_service.SubmissionRepository",
                autospec=True,
            ) as mock_repo_class,
            patch(
                "learn_to_cloud.services.submissions_service.VerificationJobRepository",
                autospec=True,
            ) as mock_job_repo_class,
        ):
            mock_repo = MagicMock()
            mock_repo.get_by_user_and_requirement = AsyncMock(
                return_value=_make_mock_submission()
            )
            mock_repo_class.return_value = mock_repo

            mock_job = MagicMock()
            mock_job_repo = MagicMock()
            mock_job_repo.create_or_get_active = AsyncMock(
                return_value=(mock_job, True)
            )
            mock_job_repo_class.return_value = mock_job_repo

            result = await create_verification_job(
                session_maker=mock_session_maker,
                user_id=123,
                requirement_slug="test-requirement",
                submitted_value="https://github.com/user/repo",
                github_username="user",
            )

            assert isinstance(result, VerificationJobSubmission)
            assert result.job is mock_job
            assert result.created is True


@pytest.mark.unit
class TestSequentialPhaseGating:
    @pytest.mark.asyncio
    async def test_submission_blocked_when_prior_phase_incomplete(self):
        mock_session_maker = _mock_session_maker()
        mock_requirement = _make_mock_requirement(
            submission_type=SubmissionType.DEPLOYED_API,
        )

        with (
            patch(
                "learn_to_cloud.services.submissions_service.load_requirement_index",
                new_callable=AsyncMock,
                return_value=_build_index(
                    mock_requirement,
                    phase_id=4,
                    prereq_phase=3,
                    prereq_req_ids=["journal-pr-logging", "journal-pr-get-entry"],
                ),
            ),
            patch(
                "learn_to_cloud.services.submissions_service.SubmissionRepository",
                autospec=True,
            ) as mock_repo_class,
        ):
            mock_repo = MagicMock()
            mock_repo.get_by_user_and_requirement = AsyncMock(return_value=None)
            mock_repo.are_all_requirements_validated = AsyncMock(return_value=False)
            mock_repo_class.return_value = mock_repo

            with pytest.raises(PriorPhaseNotCompleteError) as exc_info:
                await create_verification_job(
                    session_maker=mock_session_maker,
                    user_id=123,
                    requirement_slug="test-requirement",
                    submitted_value="https://api.example.com",
                    github_username="user",
                )

            assert exc_info.value.prerequisite_phase == 3
            assert "Phase 3" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_submission_allowed_when_prior_phase_complete(self):
        mock_session_maker = _mock_session_maker()
        mock_requirement = _make_mock_requirement(
            submission_type=SubmissionType.DEPLOYED_API,
        )

        with (
            patch(
                "learn_to_cloud.services.submissions_service.load_requirement_index",
                new_callable=AsyncMock,
                return_value=_build_index(
                    mock_requirement,
                    phase_id=4,
                    prereq_phase=3,
                    prereq_req_ids=["journal-pr-logging"],
                ),
            ),
            patch(
                "learn_to_cloud.services.submissions_service.SubmissionRepository",
                autospec=True,
            ) as mock_repo_class,
            patch(
                "learn_to_cloud.services.submissions_service.VerificationJobRepository",
                autospec=True,
            ) as mock_job_repo_class,
        ):
            mock_repo = MagicMock()
            mock_repo.get_by_user_and_requirement = AsyncMock(return_value=None)
            mock_repo.are_all_requirements_validated = AsyncMock(return_value=True)
            mock_repo_class.return_value = mock_repo

            mock_job = MagicMock()
            mock_job_repo = MagicMock()
            mock_job_repo.create_or_get_active = AsyncMock(
                return_value=(mock_job, True)
            )
            mock_job_repo_class.return_value = mock_job_repo

            result = await create_verification_job(
                session_maker=mock_session_maker,
                user_id=123,
                requirement_slug="test-requirement",
                submitted_value="https://api.example.com",
                github_username="user",
            )

            assert isinstance(result, VerificationJobSubmission)
            assert result.job is mock_job
            assert result.created is True
            mock_job_repo.create_or_get_active.assert_awaited_once()


@pytest.mark.unit
class TestCreateVerificationJob:
    @pytest.mark.asyncio
    async def test_formerly_inline_type_creates_verification_job(self):
        """Types that used to run inline (phases 0-2) now create a job too."""
        mock_session_maker = _mock_session_maker()
        mock_requirement = _make_mock_requirement(
            submission_type=SubmissionType.PROFILE_README,
        )
        mock_job = MagicMock()

        with (
            patch(
                "learn_to_cloud.services.submissions_service.load_requirement_index",
                new_callable=AsyncMock,
                return_value=_build_index(mock_requirement),
            ),
            patch(
                "learn_to_cloud.services.submissions_service.SubmissionRepository",
                autospec=True,
            ) as mock_repo_class,
            patch(
                "learn_to_cloud.services.submissions_service.VerificationJobRepository",
                autospec=True,
            ) as mock_job_repo_class,
        ):
            mock_repo = MagicMock()
            mock_repo.get_by_user_and_requirement = AsyncMock(return_value=None)
            mock_repo_class.return_value = mock_repo

            mock_job_repo = MagicMock()
            mock_job_repo.create_or_get_active = AsyncMock(
                return_value=(mock_job, True)
            )
            mock_job_repo_class.return_value = mock_job_repo

            result = await create_verification_job(
                session_maker=mock_session_maker,
                user_id=123,
                requirement_slug="test-requirement",
                submitted_value="https://github.com/user",
                github_username="user",
            )

        assert isinstance(result, VerificationJobSubmission)
        assert result.job is mock_job
        assert result.created is True
        mock_job_repo.create_or_get_active.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_returns_verification_job_submission(self):
        mock_session_maker = _mock_session_maker()
        mock_requirement = _make_mock_requirement(
            submission_type=SubmissionType.JOURNAL_API_VERIFIER,
        )
        mock_job = MagicMock()

        with (
            patch(
                "learn_to_cloud.services.submissions_service.load_requirement_index",
                new_callable=AsyncMock,
                return_value=_build_index(mock_requirement),
            ),
            patch(
                "learn_to_cloud.services.submissions_service.SubmissionRepository",
                autospec=True,
            ) as mock_repo_class,
            patch(
                "learn_to_cloud.services.submissions_service.VerificationJobRepository",
                autospec=True,
            ) as mock_job_repo_class,
        ):
            mock_repo = MagicMock()
            mock_repo.get_by_user_and_requirement = AsyncMock(return_value=None)
            mock_repo_class.return_value = mock_repo

            mock_job_repo = MagicMock()
            mock_job_repo.create_or_get_active = AsyncMock(
                return_value=(mock_job, True)
            )
            mock_job_repo_class.return_value = mock_job_repo

            result = await create_verification_job(
                session_maker=mock_session_maker,
                user_id=123,
                requirement_slug="test-requirement",
                submitted_value="https://github.com/user/repo",
                github_username="user",
            )

        assert isinstance(result, VerificationJobSubmission)
        assert result.job is mock_job
        assert result.created is True
        mock_job_repo.create_or_get_active.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_preconditions_still_enforced(self):
        mock_session_maker = _mock_session_maker()
        mock_requirement = _make_mock_requirement(
            submission_type=SubmissionType.CTF_TOKEN,
        )

        with (
            patch(
                "learn_to_cloud.services.submissions_service.load_requirement_index",
                new_callable=AsyncMock,
                return_value=_build_index(mock_requirement),
            ),
            patch(
                "learn_to_cloud.services.submissions_service.SubmissionRepository",
                autospec=True,
            ) as mock_repo_class,
            patch(
                "learn_to_cloud.services.submissions_service.VerificationJobRepository",
                autospec=True,
            ) as mock_job_repo_class,
        ):
            mock_repo = MagicMock()
            mock_repo.get_by_user_and_requirement = AsyncMock(
                return_value=MagicMock(is_validated=True)
            )
            mock_repo_class.return_value = mock_repo

            with pytest.raises(AlreadyValidatedError):
                await create_verification_job(
                    session_maker=mock_session_maker,
                    user_id=123,
                    requirement_slug="test-requirement",
                    submitted_value="some-token",
                    github_username="user",
                )

        mock_job_repo_class.assert_not_called()


# ---------------------------------------------------------------------------
# get_phase_submission_context
# ---------------------------------------------------------------------------


def _phase_with_requirement(req: HandsOnRequirement) -> Phase:
    from uuid import uuid4

    from learn_to_cloud_shared.schemas import PhaseHandsOnVerificationOverview

    return Phase(
        uuid=uuid4(),
        name="Phase 3",
        slug="phase3",
        order=3,
        topics=[],
        hands_on_verification=PhaseHandsOnVerificationOverview(
            requirements=[req],
        ),
    )


@pytest.mark.unit
class TestGetPhaseSubmissionContext:
    @pytest.mark.asyncio
    async def test_empty_submissions(self):
        req = _make_mock_requirement()
        phase = _phase_with_requirement(req)
        with patch(
            "learn_to_cloud.services.submissions_service.SubmissionRepository",
            autospec=True,
        ) as MockRepo:
            MockRepo.return_value.get_latest_for_requirements = AsyncMock(
                return_value=[]
            )
            result = await get_phase_submission_context(
                AsyncMock(), user_id=1, phase=phase
            )
        assert result.submissions_by_req == {}
        assert result.feedback_by_req == {}

    @pytest.mark.asyncio
    async def test_submission_without_feedback(self):
        req = _make_mock_requirement()
        phase = _phase_with_requirement(req)
        mock_sub = _make_mock_submission(is_validated=True)
        mock_sub.requirement_uuid = req.uuid
        mock_sub.feedback_json = None
        with patch(
            "learn_to_cloud.services.submissions_service.SubmissionRepository",
            autospec=True,
        ) as MockRepo:
            MockRepo.return_value.get_latest_for_requirements = AsyncMock(
                return_value=[mock_sub]
            )
            result = await get_phase_submission_context(
                AsyncMock(), user_id=1, phase=phase
            )
        assert req.slug in result.submissions_by_req
        assert result.feedback_by_req == {}

    @pytest.mark.asyncio
    async def test_passing_submission_with_feedback_renders_for_pass(self):
        """#425: rubric feedback persists for passing submissions too."""
        req = _make_mock_requirement()
        phase = _phase_with_requirement(req)
        mock_sub = _make_mock_submission(is_validated=True, verification_completed=True)
        mock_sub.requirement_uuid = req.uuid
        mock_sub.feedback_json = [
            {
                "task_name": "rubric-check-1",
                "passed": True,
                "feedback": "great job",
                "next_steps": "",
            },
            {
                "task_name": "rubric-check-2",
                "passed": True,
                "feedback": "also good",
                "next_steps": "",
            },
        ]
        with patch(
            "learn_to_cloud.services.submissions_service.SubmissionRepository",
            autospec=True,
        ) as MockRepo:
            MockRepo.return_value.get_latest_for_requirements = AsyncMock(
                return_value=[mock_sub]
            )
            result = await get_phase_submission_context(
                AsyncMock(), user_id=1, phase=phase
            )
        assert req.slug in result.feedback_by_req
        feedback = result.feedback_by_req[req.slug]
        assert feedback["passed"] == 2
        tasks = cast(list[dict[str, object]], feedback["tasks"])
        assert len(tasks) == 2
        assert all(t["passed"] is True for t in tasks)
        req = _make_mock_requirement()
        phase = _phase_with_requirement(req)
        mock_sub = _make_mock_submission(
            is_validated=False, verification_completed=True
        )
        mock_sub.requirement_uuid = req.uuid
        mock_sub.feedback_json = [
            {
                "task_name": "A",
                "passed": True,
                "feedback": "ok",
                "next_steps": "review the rubric",
            }
        ]
        with patch(
            "learn_to_cloud.services.submissions_service.SubmissionRepository",
            autospec=True,
        ) as MockRepo:
            MockRepo.return_value.get_latest_for_requirements = AsyncMock(
                return_value=[mock_sub]
            )
            result = await get_phase_submission_context(
                AsyncMock(), user_id=1, phase=phase
            )
        assert req.slug in result.feedback_by_req
        feedback = result.feedback_by_req[req.slug]
        assert feedback["passed"] == 1
        assert feedback["tasks"] == [
            {
                "name": "A",
                "passed": True,
                "message": "ok",
                "next_steps": "review the rubric",
            }
        ]


@pytest.mark.unit
class TestRunSubmitSmokeCheck:
    """Tests for the read-only post-deploy verification smoke check."""

    def test_pick_smoke_requirement_returns_earliest_phase(self):
        """The canary picks the first requirement of the earliest phase."""
        from learn_to_cloud_shared.testing.requirement_factories import (
            journal_api_verifier_requirement,
        )

        early = journal_api_verifier_requirement(
            slug="early", name="early", description="early"
        )
        late = journal_api_verifier_requirement(
            slug="late", name="late", description="late"
        )
        index = RequirementIndex(
            by_phase_order={5: [late], 0: [early]},
            by_slug={"early": early, "late": late},
            phase_order_by_req_slug={"early": 0, "late": 5},
        )

        assert pick_smoke_requirement(index).slug == "early"

    def test_pick_smoke_requirement_raises_when_no_requirements(self):
        """An empty index is itself a failure worth surfacing."""
        with pytest.raises(RuntimeError):
            pick_smoke_requirement(RequirementIndex())

    @pytest.mark.asyncio
    async def test_smoke_check_exercises_read_path_without_writes(self):
        """The canary reads for the synthetic user and writes nothing."""
        mock_session_maker = _mock_session_maker()
        mock_requirement = _make_mock_requirement()

        with (
            patch(
                "learn_to_cloud.services.submissions_service.load_requirement_index",
                new_callable=AsyncMock,
                return_value=_build_index(mock_requirement),
            ),
            patch(
                "learn_to_cloud.services.submissions_service.SubmissionRepository",
                autospec=True,
            ) as mock_repo_class,
            patch(
                "learn_to_cloud.services.submissions_service.VerificationJobRepository",
                autospec=True,
            ) as mock_job_repo_class,
        ):
            mock_repo = MagicMock()
            mock_repo.get_by_user_and_requirement = AsyncMock(return_value=None)
            mock_repo.are_all_requirements_validated = AsyncMock(return_value=True)
            mock_repo_class.return_value = mock_repo

            result = await run_submit_smoke_check(mock_session_maker)

        assert result["requirement_slug"] == mock_requirement.slug
        # Reads use the synthetic, non-existent user id.
        mock_repo.get_by_user_and_requirement.assert_awaited_once_with(
            SMOKE_USER_ID, mock_requirement.uuid
        )
        # The canary never creates a verification job (no writes).
        mock_job_repo_class.assert_not_called()

    @pytest.mark.asyncio
    async def test_smoke_check_propagates_read_errors(self):
        """A schema/code mismatch surfaces as a raised error, not a clean pass."""
        mock_session_maker = _mock_session_maker()
        mock_requirement = _make_mock_requirement()

        with (
            patch(
                "learn_to_cloud.services.submissions_service.load_requirement_index",
                new_callable=AsyncMock,
                return_value=_build_index(mock_requirement),
            ),
            patch(
                "learn_to_cloud.services.submissions_service.SubmissionRepository",
                autospec=True,
            ) as mock_repo_class,
        ):
            mock_repo = MagicMock()
            mock_repo.get_by_user_and_requirement = AsyncMock(
                side_effect=RuntimeError("column submissions.foo does not exist")
            )
            mock_repo_class.return_value = mock_repo

            with pytest.raises(RuntimeError):
                await run_submit_smoke_check(mock_session_maker)
