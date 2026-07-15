"""Tests for submissions_service verification job pre-validation and the
phase submission card context.

Tests cover:
- Already-validated short-circuit (authoritative + legacy fallback)
- Sequential phase gating (authoritative + legacy fallback)
- get_phase_submission_context: authoritative-attempt cards, every terminal
  outcome, active-attempt suppression, and legacy-only fallback
"""

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import cast
from unittest.mock import ANY, AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from learn_to_cloud_shared.models import SubmissionType, SubmissionValueKind
from learn_to_cloud_shared.repositories.verification_attempt_repository import (
    AttemptAlreadyValidatedError,
    AttemptCardProjection,
)
from learn_to_cloud_shared.requirements import RequirementIndex
from learn_to_cloud_shared.schemas import HandsOnRequirement, Phase

from learn_to_cloud.services.submissions_service import (
    _SMOKE_USER_ID as SMOKE_USER_ID,
)
from learn_to_cloud.services.submissions_service import (
    AlreadyValidatedError,
    PriorPhaseNotCompleteError,
    RequirementNotFoundError,
    VerificationAttemptSubmission,
    create_verification_attempt,
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
    an AsyncMock session. Since tests patch the repository layer, the
    actual session object is irrelevant -- it just needs to support the
    async-with protocol and have a .commit() coroutine.
    """

    @asynccontextmanager
    async def _factory():
        yield AsyncMock()

    return _factory


def _mock_attempt(attempt_id=None) -> MagicMock:
    """Create a mock VerificationAttempt with an ``id`` for submission tests."""
    return MagicMock(id=attempt_id or uuid4())


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


def _gating_mock(
    requirement_uuid,
    *,
    already_validated: bool = False,
    prereq_satisfied: bool = True,
):
    """Build an ``are_all_requirements_succeeded`` stand-in for gating tests.

    The real ``_check_submission_preconditions`` calls the shared
    ``are_all_requirements_succeeded`` helper twice with different UUID
    lists (the single requirement being submitted, then any prerequisite
    phase's requirements) -- this dispatches on the exact single-UUID list
    so both call sites can be controlled independently in one mock.
    """

    async def _fn(_db, _user_id, uuids):
        uuids = list(uuids)
        if uuids == [requirement_uuid]:
            return already_validated
        return prereq_satisfied

    return AsyncMock(side_effect=_fn)


@pytest.mark.unit
class TestSubmissionValidationErrors:
    """Tests for error handling in create_verification_attempt."""

    @pytest.mark.asyncio
    async def test_requirement_not_found_raises_error(self):
        mock_session_maker = _mock_session_maker()

        with (
            patch(
                "learn_to_cloud.services.submissions_service.load_requirement_index",
                return_value=_build_index(None),
            ),
            pytest.raises(RequirementNotFoundError),
        ):
            await create_verification_attempt(
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
        """Authoritative-or-legacy succeeded (via ``are_all_requirements_succeeded``)
        short-circuits before any attempt is created."""
        mock_session_maker = _mock_session_maker()
        mock_requirement = _make_mock_requirement()

        with (
            patch(
                "learn_to_cloud.services.submissions_service.load_requirement_index",
                return_value=_build_index(mock_requirement),
            ),
            patch(
                "learn_to_cloud.services.submissions_service.are_all_requirements_succeeded",
                new=_gating_mock(mock_requirement.uuid, already_validated=True),
            ),
            patch(
                "learn_to_cloud.services.submissions_service.VerificationAttemptRepository",
                autospec=True,
            ) as mock_attempt_repo_class,
        ):
            with pytest.raises(AlreadyValidatedError):
                await create_verification_attempt(
                    session_maker=mock_session_maker,
                    user_id=123,
                    requirement_slug="test-requirement",
                    submitted_value="https://github.com/user/repo",
                    github_username="user",
                )

        mock_attempt_repo_class.assert_not_called()

    @pytest.mark.asyncio
    async def test_already_validated_attempt_raises_error(self):
        """A succeeded attempt discovered under the advisory lock (a race
        with a concurrent finalize) also raises AlreadyValidatedError, even
        though the earlier precondition check passed."""
        mock_session_maker = _mock_session_maker()
        mock_requirement = _make_mock_requirement()

        with (
            patch(
                "learn_to_cloud.services.submissions_service.load_requirement_index",
                return_value=_build_index(mock_requirement),
            ),
            patch(
                "learn_to_cloud.services.submissions_service.are_all_requirements_succeeded",
                new=_gating_mock(mock_requirement.uuid, already_validated=False),
            ),
            patch(
                "learn_to_cloud.services.submissions_service."
                "VerificationAttemptRepository",
                autospec=True,
            ) as mock_attempt_repo_class,
        ):
            mock_attempt_repo = MagicMock()
            mock_attempt_repo.create_or_get_active = AsyncMock(
                side_effect=AttemptAlreadyValidatedError("already succeeded")
            )
            mock_attempt_repo_class.return_value = mock_attempt_repo

            with pytest.raises(AlreadyValidatedError):
                await create_verification_attempt(
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
                return_value=_build_index(mock_requirement),
            ),
            patch(
                "learn_to_cloud.services.submissions_service.are_all_requirements_succeeded",
                new=_gating_mock(mock_requirement.uuid, already_validated=False),
            ),
            patch(
                "learn_to_cloud.services.submissions_service."
                "VerificationAttemptRepository",
                autospec=True,
            ) as mock_attempt_repo_class,
        ):
            mock_attempt = _mock_attempt()
            mock_attempt_repo = MagicMock()
            mock_attempt_repo.create_or_get_active = AsyncMock(
                return_value=(mock_attempt, True)
            )
            mock_attempt_repo_class.return_value = mock_attempt_repo

            result = await create_verification_attempt(
                session_maker=mock_session_maker,
                user_id=123,
                requirement_slug="test-requirement",
                submitted_value="https://github.com/user/repo",
                github_username="user",
            )

            assert isinstance(result, VerificationAttemptSubmission)
            assert result.attempt_id == mock_attempt.id
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
                return_value=_build_index(
                    mock_requirement,
                    phase_id=4,
                    prereq_phase=3,
                    prereq_req_ids=["journal-pr-logging", "journal-pr-get-entry"],
                ),
            ),
            patch(
                "learn_to_cloud.services.submissions_service.are_all_requirements_succeeded",
                new=_gating_mock(
                    mock_requirement.uuid,
                    already_validated=False,
                    prereq_satisfied=False,
                ),
            ),
        ):
            with pytest.raises(PriorPhaseNotCompleteError) as exc_info:
                await create_verification_attempt(
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
                return_value=_build_index(
                    mock_requirement,
                    phase_id=4,
                    prereq_phase=3,
                    prereq_req_ids=["journal-pr-logging"],
                ),
            ),
            patch(
                "learn_to_cloud.services.submissions_service.are_all_requirements_succeeded",
                new=_gating_mock(
                    mock_requirement.uuid,
                    already_validated=False,
                    prereq_satisfied=True,
                ),
            ),
            patch(
                "learn_to_cloud.services.submissions_service."
                "VerificationAttemptRepository",
                autospec=True,
            ) as mock_attempt_repo_class,
        ):
            mock_attempt = _mock_attempt()
            mock_attempt_repo = MagicMock()
            mock_attempt_repo.create_or_get_active = AsyncMock(
                return_value=(mock_attempt, True)
            )
            mock_attempt_repo_class.return_value = mock_attempt_repo

            result = await create_verification_attempt(
                session_maker=mock_session_maker,
                user_id=123,
                requirement_slug="test-requirement",
                submitted_value="https://api.example.com",
                github_username="user",
            )

            assert isinstance(result, VerificationAttemptSubmission)
            assert result.attempt_id == mock_attempt.id
            assert result.created is True
            mock_attempt_repo.create_or_get_active.assert_awaited_once()


@pytest.mark.unit
class TestCreateVerificationAttempt:
    @pytest.mark.asyncio
    async def test_formerly_inline_type_creates_verification_attempt(self):
        """Types that used to run inline (phases 0-2) now create an attempt too."""
        mock_session_maker = _mock_session_maker()
        mock_requirement = _make_mock_requirement(
            submission_type=SubmissionType.PROFILE_README,
        )
        mock_attempt = _mock_attempt()

        with (
            patch(
                "learn_to_cloud.services.submissions_service.load_requirement_index",
                return_value=_build_index(mock_requirement),
            ),
            patch(
                "learn_to_cloud.services.submissions_service.are_all_requirements_succeeded",
                new=_gating_mock(mock_requirement.uuid, already_validated=False),
            ),
            patch(
                "learn_to_cloud.services.submissions_service."
                "VerificationAttemptRepository",
                autospec=True,
            ) as mock_attempt_repo_class,
            patch(
                "learn_to_cloud.services.submissions_service._current_traceparent",
                return_value=(
                    "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
                ),
            ),
        ):
            mock_attempt_repo = MagicMock()
            mock_attempt_repo.create_or_get_active = AsyncMock(
                return_value=(mock_attempt, True)
            )
            mock_attempt_repo_class.return_value = mock_attempt_repo

            result = await create_verification_attempt(
                session_maker=mock_session_maker,
                user_id=123,
                requirement_slug="test-requirement",
                submitted_value="https://github.com/user",
                github_username="user",
            )

        assert isinstance(result, VerificationAttemptSubmission)
        assert result.attempt_id == mock_attempt.id
        assert result.created is True
        mock_attempt_repo.create_or_get_active.assert_awaited_once()
        expected_traceparent = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
        attempt_create_await_args = mock_attempt_repo.create_or_get_active.await_args
        assert attempt_create_await_args is not None
        assert attempt_create_await_args.kwargs["traceparent"] == expected_traceparent
        assert attempt_create_await_args.kwargs["legacy_job_id"] is None

    @pytest.mark.asyncio
    async def test_returns_verification_attempt_submission(self):
        mock_session_maker = _mock_session_maker()
        mock_requirement = _make_mock_requirement(
            submission_type=SubmissionType.JOURNAL_API_VERIFIER,
        )
        mock_attempt = _mock_attempt()

        with (
            patch(
                "learn_to_cloud.services.submissions_service.load_requirement_index",
                return_value=_build_index(mock_requirement),
            ),
            patch(
                "learn_to_cloud.services.submissions_service.are_all_requirements_succeeded",
                new=_gating_mock(mock_requirement.uuid, already_validated=False),
            ),
            patch(
                "learn_to_cloud.services.submissions_service."
                "VerificationAttemptRepository",
                autospec=True,
            ) as mock_attempt_repo_class,
        ):
            mock_attempt_repo = MagicMock()
            mock_attempt_repo.create_or_get_active = AsyncMock(
                return_value=(mock_attempt, True)
            )
            mock_attempt_repo_class.return_value = mock_attempt_repo

            result = await create_verification_attempt(
                session_maker=mock_session_maker,
                user_id=123,
                requirement_slug="test-requirement",
                submitted_value="https://github.com/user/repo",
                github_username="user",
            )

        assert isinstance(result, VerificationAttemptSubmission)
        assert result.attempt_id == mock_attempt.id
        assert result.created is True
        mock_attempt_repo.create_or_get_active.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_concurrent_submit_reuses_active_attempt(self):
        mock_session_maker = _mock_session_maker()
        mock_requirement = _make_mock_requirement(
            submission_type=SubmissionType.JOURNAL_API_VERIFIER,
        )
        mock_attempt = _mock_attempt()

        with (
            patch(
                "learn_to_cloud.services.submissions_service.load_requirement_index",
                return_value=_build_index(mock_requirement),
            ),
            patch(
                "learn_to_cloud.services.submissions_service.are_all_requirements_succeeded",
                new=_gating_mock(mock_requirement.uuid, already_validated=False),
            ),
            patch(
                "learn_to_cloud.services.submissions_service."
                "VerificationAttemptRepository",
                autospec=True,
            ) as mock_attempt_repo_class,
        ):
            mock_attempt_repo = MagicMock()
            mock_attempt_repo.create_or_get_active = AsyncMock(
                return_value=(mock_attempt, False)
            )
            mock_attempt_repo_class.return_value = mock_attempt_repo

            result = await create_verification_attempt(
                session_maker=mock_session_maker,
                user_id=123,
                requirement_slug="test-requirement",
                submitted_value="https://github.com/user/repo",
                github_username="user",
            )

        assert result.attempt_id == mock_attempt.id
        assert result.created is False

    @pytest.mark.asyncio
    async def test_preconditions_still_enforced(self):
        mock_session_maker = _mock_session_maker()
        mock_requirement = _make_mock_requirement(
            submission_type=SubmissionType.CTF_TOKEN,
        )

        with (
            patch(
                "learn_to_cloud.services.submissions_service.load_requirement_index",
                return_value=_build_index(mock_requirement),
            ),
            patch(
                "learn_to_cloud.services.submissions_service.are_all_requirements_succeeded",
                new=_gating_mock(mock_requirement.uuid, already_validated=True),
            ),
            patch(
                "learn_to_cloud.services.submissions_service."
                "VerificationAttemptRepository",
                autospec=True,
            ) as mock_attempt_repo_class,
        ):
            with pytest.raises(AlreadyValidatedError):
                await create_verification_attempt(
                    session_maker=mock_session_maker,
                    user_id=123,
                    requirement_slug="test-requirement",
                    submitted_value="some-token",
                    github_username="user",
                )

        mock_attempt_repo_class.assert_not_called()


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


def _make_attempt_projection(
    req: HandsOnRequirement,
    *,
    outcome: str,
    feedback_json: list[dict] | None = None,
    validation_message: str | None = None,
) -> AttemptCardProjection:
    now = datetime.now(UTC)
    return AttemptCardProjection(
        id=uuid4(),
        requirement_uuid=req.uuid,
        submission_value_kind=SubmissionValueKind.GITHUB_URL.value,
        submitted_value="https://github.com/user/repo",
        github_username_snapshot="user",
        cloud_provider=None,
        outcome=outcome,
        feedback_json=feedback_json,
        validation_message=validation_message,
        completed_at=now,
        created_at=now,
        updated_at=now,
    )


def _patch_attempt_repo(
    *,
    latest_terminal: list[AttemptCardProjection] | None = None,
    attempted_uuids: set | None = None,
):
    """Patch VerificationAttemptRepository for get_phase_submission_context tests."""
    return patch(
        "learn_to_cloud.services.submissions_service.VerificationAttemptRepository",
        autospec=True,
        return_value=MagicMock(
            get_latest_terminal_for_requirements=AsyncMock(
                return_value=latest_terminal or []
            ),
            get_requirement_uuids_with_any_attempt=AsyncMock(
                return_value=attempted_uuids
                if attempted_uuids is not None
                else {p.requirement_uuid for p in (latest_terminal or [])}
            ),
        ),
    )


@pytest.mark.unit
class TestGetPhaseSubmissionContext:
    @pytest.mark.asyncio
    async def test_empty_when_no_attempts_and_no_legacy_submissions(self):
        req = _make_mock_requirement()
        phase = _phase_with_requirement(req)
        with (
            _patch_attempt_repo(latest_terminal=[], attempted_uuids=set()),
            patch(
                "learn_to_cloud.services.submissions_service.SubmissionRepository",
                autospec=True,
            ) as MockRepo,
        ):
            MockRepo.return_value.get_latest_for_requirements = AsyncMock(
                return_value=[]
            )
            result = await get_phase_submission_context(
                AsyncMock(), user_id=1, phase=phase
            )
        assert result.submissions_by_req == {}
        assert result.feedback_by_req == {}

    @pytest.mark.asyncio
    async def test_succeeded_attempt_renders_as_validated(self):
        """A ``succeeded`` attempt is the authoritative source for the card."""
        req = _make_mock_requirement()
        phase = _phase_with_requirement(req)
        attempt = _make_attempt_projection(req, outcome="succeeded")

        with _patch_attempt_repo(latest_terminal=[attempt]):
            result = await get_phase_submission_context(
                AsyncMock(), user_id=1, phase=phase
            )

        assert req.slug in result.submissions_by_req
        sub = result.submissions_by_req[req.slug]
        assert sub.is_validated is True
        assert sub.verification_completed is True
        assert sub.source == "attempt"

    @pytest.mark.asyncio
    async def test_failed_attempt_renders_as_not_validated_but_completed(self):
        req = _make_mock_requirement()
        phase = _phase_with_requirement(req)
        attempt = _make_attempt_projection(
            req, outcome="failed", validation_message="Repo not found."
        )

        with _patch_attempt_repo(latest_terminal=[attempt]):
            result = await get_phase_submission_context(
                AsyncMock(), user_id=1, phase=phase
            )

        sub = result.submissions_by_req[req.slug]
        assert sub.is_validated is False
        assert sub.verification_completed is True
        assert sub.validation_message == "Repo not found."

    @pytest.mark.asyncio
    async def test_server_error_attempt_does_not_count_as_completed(self):
        """A server-side fault never completed verification -- doesn't count
        against the learner, distinct from a real ``failed`` outcome."""
        req = _make_mock_requirement()
        phase = _phase_with_requirement(req)
        attempt = _make_attempt_projection(req, outcome="server_error")

        with _patch_attempt_repo(latest_terminal=[attempt]):
            result = await get_phase_submission_context(
                AsyncMock(), user_id=1, phase=phase
            )

        sub = result.submissions_by_req[req.slug]
        assert sub.is_validated is False
        assert sub.verification_completed is False

    @pytest.mark.asyncio
    async def test_cancelled_attempt_does_not_count_as_completed(self):
        req = _make_mock_requirement()
        phase = _phase_with_requirement(req)
        attempt = _make_attempt_projection(req, outcome="cancelled")

        with _patch_attempt_repo(latest_terminal=[attempt]):
            result = await get_phase_submission_context(
                AsyncMock(), user_id=1, phase=phase
            )

        sub = result.submissions_by_req[req.slug]
        assert sub.is_validated is False
        assert sub.verification_completed is False

    @pytest.mark.asyncio
    async def test_active_attempt_suppresses_card_without_legacy_fallback(self):
        """An active (still-processing) attempt means "no terminal card yet",
        and must NOT fall back to legacy data even if a legacy row exists --
        an authoritative attempt (any state) always wins over legacy."""
        req = _make_mock_requirement()
        phase = _phase_with_requirement(req)

        with (
            _patch_attempt_repo(latest_terminal=[], attempted_uuids={req.uuid}),
            patch(
                "learn_to_cloud.services.submissions_service.SubmissionRepository",
                autospec=True,
            ) as MockRepo,
        ):
            result = await get_phase_submission_context(
                AsyncMock(), user_id=1, phase=phase
            )

        assert result.submissions_by_req == {}
        MockRepo.return_value.get_latest_for_requirements.assert_not_called()

    @pytest.mark.asyncio
    async def test_legacy_fallback_used_only_when_no_attempt_exists(self):
        """Zero attempt rows for a requirement is the only case that
        consults the legacy ``submissions`` table."""
        req = _make_mock_requirement()
        phase = _phase_with_requirement(req)
        mock_sub = _make_mock_submission(is_validated=True)
        mock_sub.requirement_uuid = req.uuid
        mock_sub.feedback_json = None

        with (
            _patch_attempt_repo(latest_terminal=[], attempted_uuids=set()),
            patch(
                "learn_to_cloud.services.submissions_service.SubmissionRepository",
                autospec=True,
            ) as MockRepo,
        ):
            MockRepo.return_value.get_latest_for_requirements = AsyncMock(
                return_value=[mock_sub]
            )
            result = await get_phase_submission_context(
                AsyncMock(), user_id=1, phase=phase
            )

        assert req.slug in result.submissions_by_req
        sub = result.submissions_by_req[req.slug]
        assert sub.source == "legacy"
        assert sub.is_validated is True

    @pytest.mark.asyncio
    async def test_authoritative_attempt_wins_over_legacy_when_both_exist(self):
        """A requirement with an attempt row is never re-checked against
        legacy data, even if a (stale) legacy row also exists."""
        req = _make_mock_requirement()
        phase = _phase_with_requirement(req)
        attempt = _make_attempt_projection(req, outcome="succeeded")

        with (
            _patch_attempt_repo(latest_terminal=[attempt], attempted_uuids={req.uuid}),
            patch(
                "learn_to_cloud.services.submissions_service.SubmissionRepository",
                autospec=True,
            ) as MockRepo,
        ):
            result = await get_phase_submission_context(
                AsyncMock(), user_id=1, phase=phase
            )

        assert result.submissions_by_req[req.slug].source == "attempt"
        MockRepo.return_value.get_latest_for_requirements.assert_not_called()

    @pytest.mark.asyncio
    async def test_passing_submission_with_feedback_renders_for_pass(self):
        """#425: rubric feedback persists for passing submissions too --
        exercised here via the legacy fallback path."""
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
        with (
            _patch_attempt_repo(latest_terminal=[], attempted_uuids=set()),
            patch(
                "learn_to_cloud.services.submissions_service.SubmissionRepository",
                autospec=True,
            ) as MockRepo,
        ):
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

    @pytest.mark.asyncio
    async def test_attempt_feedback_renders_for_pass(self):
        """Rubric feedback surfaces from an authoritative attempt too."""
        req = _make_mock_requirement()
        phase = _phase_with_requirement(req)
        attempt = _make_attempt_projection(
            req,
            outcome="failed",
            feedback_json=[
                {
                    "task_name": "A",
                    "passed": True,
                    "feedback": "ok",
                    "next_steps": "review the rubric",
                }
            ],
        )

        with _patch_attempt_repo(latest_terminal=[attempt]):
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
                return_value=_build_index(mock_requirement),
            ),
            patch(
                "learn_to_cloud.services.submissions_service.are_all_requirements_succeeded",
                new=_gating_mock(mock_requirement.uuid, already_validated=False),
            ) as mock_gate,
        ):
            result = await run_submit_smoke_check(mock_session_maker)

        assert result["requirement_slug"] == mock_requirement.slug
        # Reads use the synthetic, non-existent user id.
        mock_gate.assert_awaited_once_with(ANY, SMOKE_USER_ID, [mock_requirement.uuid])

    @pytest.mark.asyncio
    async def test_smoke_check_propagates_read_errors(self):
        """A schema/code mismatch surfaces as a raised error, not a clean pass."""
        mock_session_maker = _mock_session_maker()
        mock_requirement = _make_mock_requirement()

        with (
            patch(
                "learn_to_cloud.services.submissions_service.load_requirement_index",
                return_value=_build_index(mock_requirement),
            ),
            patch(
                "learn_to_cloud.services.submissions_service.are_all_requirements_succeeded",
                new=AsyncMock(
                    side_effect=RuntimeError("column submissions.foo does not exist")
                ),
            ),
        ):
            with pytest.raises(RuntimeError):
                await run_submit_smoke_check(mock_session_maker)
