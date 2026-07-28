"""Unit tests for progress_service.

Tests cover:
- compute_topic_progress status derivation and stale-step filtering
- phase_progress_to_data status mapping
- fetch_user_progress DB assembly from authoritative learner state
- fetch_phase_progress per-topic breakdown, including zero-requirement phases
- both-measures phase completion (learning AND verification)
- find_first_incomplete_step / resolve_continue_destination
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from learn_to_cloud_shared.schemas import (
    LearningProgress,
    LearningStep,
    Phase,
    PhaseHandsOnVerificationOverview,
    PhaseProgress,
    Topic,
    VerificationProgress,
)
from learn_to_cloud_shared.testing.requirement_factories import (
    repo_fork_requirement,
)

from learn_to_cloud.services.progress_service import (
    compute_topic_progress,
    fetch_phase_progress,
    fetch_user_progress,
    find_first_incomplete_step,
    phase_progress_to_data,
    resolve_continue_destination,
)

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _make_step(step_id: str, order: int = 0) -> LearningStep:
    return LearningStep(
        uuid=uuid4(), slug=step_id, order=order, title=f"Step {step_id}"
    )


def _make_topic(
    topic_id: str = "phase0-topic1",
    steps: list[str] | None = None,
) -> Topic:
    step_ids = steps if steps is not None else ["s1", "s2", "s3"]
    return Topic(
        uuid=uuid4(),
        slug="topic1",
        name="Test Topic",
        description="A test topic",
        order=0,
        learning_steps=[_make_step(sid, i) for i, sid in enumerate(step_ids)],
    )


def _make_phase(
    phase_id: int = 0,
    topics: list[Topic] | None = None,
) -> Phase:
    return Phase(
        uuid=uuid4(),
        name=f"Phase {phase_id}",
        slug=f"phase{phase_id}",
        order=phase_id,
        topics=topics or [],
    )


def _with_requirement(phase: Phase) -> Phase:
    return phase.model_copy(
        update={
            "hands_on_verification": PhaseHandsOnVerificationOverview(
                requirements=[repo_fork_requirement(slug="verify")]
            )
        }
    )


# ---------------------------------------------------------------------------
# compute_topic_progress (pure function -- no mocking needed)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestComputeTopicProgress:
    def test_no_steps_completed(self):
        topic = _make_topic(steps=["s1", "s2", "s3"])
        result = compute_topic_progress(topic, set())
        assert result.status == "not_started"
        assert result.percentage == 0.0
        assert result.steps_completed == 0
        assert result.steps_total == 3

    def test_partial_progress(self):
        topic = _make_topic(steps=["s1", "s2", "s3"])
        result = compute_topic_progress(topic, {"s1"})
        assert result.status == "in_progress"
        assert result.percentage == pytest.approx(33.3, abs=0.1)
        assert result.steps_completed == 1

    def test_all_steps_completed(self):
        topic = _make_topic(steps=["s1", "s2"])
        result = compute_topic_progress(topic, {"s1", "s2"})
        assert result.status == "completed"
        assert result.percentage == 100.0

    def test_stale_step_ids_filtered(self):
        topic = _make_topic(steps=["s1", "s2"])
        result = compute_topic_progress(topic, {"s1", "s3_stale"})
        assert result.steps_completed == 1
        assert result.percentage == 50.0

    def test_zero_step_topic(self):
        topic = _make_topic(steps=[])
        result = compute_topic_progress(topic, set())
        assert result.status == "completed"
        assert result.percentage == 100.0

    def test_superset_of_steps_caps_at_total(self):
        topic = _make_topic(steps=["s1"])
        result = compute_topic_progress(topic, {"s1"})
        assert result.steps_completed == 1
        assert result.steps_total == 1


# ---------------------------------------------------------------------------
# phase_progress_to_data
# ---------------------------------------------------------------------------


def _phase_progress(
    *,
    steps_completed: int = 0,
    steps_required: int = 5,
    requirements_verified: int = 0,
    requirements_required: int = 1,
) -> PhaseProgress:
    return PhaseProgress(
        phase_id=0,
        learning=LearningProgress(
            steps_completed=steps_completed, steps_required=steps_required
        ),
        verification=VerificationProgress(
            requirements_verified=requirements_verified,
            requirements_required=requirements_required,
        ),
    )


@pytest.mark.unit
class TestPhaseProgressToData:
    def test_completed_status(self):
        progress = _phase_progress(
            steps_completed=5,
            steps_required=5,
            requirements_verified=1,
            requirements_required=1,
        )
        data = phase_progress_to_data(progress)
        assert data.status == "completed"
        assert data.is_complete is True

    def test_in_progress_from_steps(self):
        progress = _phase_progress(
            steps_completed=2,
            steps_required=5,
            requirements_verified=0,
            requirements_required=1,
        )
        data = phase_progress_to_data(progress)
        assert data.status == "in_progress"

    def test_in_progress_from_verification_only(self):
        progress = _phase_progress(
            steps_completed=0,
            steps_required=5,
            requirements_verified=1,
            requirements_required=2,
        )
        data = phase_progress_to_data(progress)
        assert data.status == "in_progress"

    def test_not_started(self):
        progress = _phase_progress(
            steps_completed=0,
            steps_required=5,
            requirements_verified=0,
            requirements_required=1,
        )
        data = phase_progress_to_data(progress)
        assert data.status == "not_started"

    def test_not_complete_when_only_learning_done(self):
        """Both measures must be complete -- learning alone isn't enough."""
        progress = _phase_progress(
            steps_completed=5,
            steps_required=5,
            requirements_verified=0,
            requirements_required=1,
        )
        assert progress.is_complete is False
        assert progress.status == "learning_complete"

    def test_not_complete_when_only_verification_done(self):
        """Both measures must be complete -- verification alone isn't enough."""
        progress = _phase_progress(
            steps_completed=0,
            steps_required=5,
            requirements_verified=1,
            requirements_required=1,
        )
        assert progress.is_complete is False
        assert progress.status == "verification_complete"

    def test_zero_requirements_is_verification_complete(self):
        """A phase with zero requirements is verification-complete by definition."""
        progress = _phase_progress(
            steps_completed=5,
            steps_required=5,
            requirements_verified=0,
            requirements_required=0,
        )
        assert progress.verification.is_complete is True
        assert progress.is_complete is True

    def test_zero_steps_is_learning_complete(self):
        """A phase with zero steps is learning-complete by definition."""
        progress = _phase_progress(
            steps_completed=0,
            steps_required=0,
            requirements_verified=1,
            requirements_required=1,
        )
        assert progress.learning.is_complete is True
        assert progress.is_complete is True

    def test_empty_phase_is_not_started(self):
        progress = _phase_progress(
            steps_completed=0,
            steps_required=0,
            requirements_verified=0,
            requirements_required=0,
        )
        assert progress.is_complete is True
        assert progress.status == "not_started"

    def test_untouched_hands_on_only_phase_is_not_started_not_learning_complete(self):
        """A zero-step, untouched hands-on-only phase reads as not started.

        Regression: naively deriving status from the trivial "zero steps
        means 100% learning" rule would label an untouched hands-on-only
        phase "learning complete", which misleads a learner who hasn't
        touched it at all.
        """
        progress = _phase_progress(
            steps_completed=0,
            steps_required=0,
            requirements_verified=0,
            requirements_required=2,
        )
        assert progress.status == "not_started"

    def test_partial_steps_only_phase_is_in_progress_not_verification_complete(self):
        """A zero-requirement phase's status is driven by steps alone.

        Regression: naively deriving status from the trivial "zero
        requirements means 100% verification" rule would label a
        partially-stepped, requirement-free phase "verification complete",
        which is vacuously true and misleading.
        """
        progress = _phase_progress(
            steps_completed=3,
            steps_required=10,
            requirements_verified=0,
            requirements_required=0,
        )
        assert progress.status == "in_progress"


# ---------------------------------------------------------------------------
# fetch_user_progress
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestFetchUserProgress:
    @pytest.mark.asyncio
    async def test_queries_db_and_returns_progress(self):
        from learn_to_cloud_shared.requirements import RequirementIndex
        from learn_to_cloud_shared.schemas import PhaseOverview

        phase_overview = (
            PhaseOverview(uuid=uuid4(), name="Phase 0", slug="phase0", order=0),
        )
        step_uuid = uuid4()
        fake_catalog = MagicMock(
            active_step_uuids=frozenset({step_uuid}),
            active_requirement_uuids=frozenset(),
            phase_order_by_step_uuid={step_uuid: 0},
            phase_order_by_requirement_uuid={},
        )

        with (
            patch(
                "learn_to_cloud.services.progress_service.get_curriculum_overview",
                return_value=phase_overview,
            ),
            patch(
                "learn_to_cloud.services.progress_service.get_required_step_counts_by_phase",
                return_value={0: 3},
            ),
            patch(
                "learn_to_cloud.services.progress_service.load_requirement_index",
                return_value=RequirementIndex(),
            ),
            patch(
                "learn_to_cloud.services.progress_service.get_curriculum_catalog",
                return_value=fake_catalog,
            ),
            patch(
                "learn_to_cloud.services.progress_service.resolve_completed_step_uuids",
                new=AsyncMock(return_value={step_uuid}),
            ),
            patch(
                "learn_to_cloud.services.progress_service.resolve_succeeded_requirement_uuids",
                new=AsyncMock(return_value=set()),
            ),
        ):
            result = await fetch_user_progress(AsyncMock(), user_id=1)
            assert result.user_id == 1
            assert result.phases[0].learning.steps_completed == 1
            assert result.phases[0].learning.steps_required == 3

    @pytest.mark.asyncio
    async def test_groups_completions_by_phase_and_ignores_stale_uuids(self):
        """Completed/succeeded UUIDs no longer in the catalog are dropped.

        Simulates a retired step and a retired requirement (completed by
        the user in the past, but the resolver still returns them because
        the repository query itself only filters on candidate UUIDs the
        caller passed in) alongside one current step and one current
        requirement, each in a different phase. A UUID absent from
        ``phase_order_by_*_uuid`` must not inflate any phase's progress.
        """
        from learn_to_cloud_shared.requirements import RequirementIndex
        from learn_to_cloud_shared.schemas import PhaseOverview

        phase_overview = (
            PhaseOverview(uuid=uuid4(), name="Phase 0", slug="phase0", order=0),
            PhaseOverview(uuid=uuid4(), name="Phase 1", slug="phase1", order=1),
        )
        current_step_uuid = uuid4()
        stale_step_uuid = uuid4()
        current_req_uuid = uuid4()
        stale_req_uuid = uuid4()
        fake_catalog = MagicMock(
            active_step_uuids=frozenset({current_step_uuid}),
            active_requirement_uuids=frozenset({current_req_uuid}),
            phase_order_by_step_uuid={current_step_uuid: 0},
            phase_order_by_requirement_uuid={current_req_uuid: 1},
        )

        with (
            patch(
                "learn_to_cloud.services.progress_service.get_curriculum_overview",
                return_value=phase_overview,
            ),
            patch(
                "learn_to_cloud.services.progress_service.get_required_step_counts_by_phase",
                return_value={0: 1, 1: 0},
            ),
            patch(
                "learn_to_cloud.services.progress_service.load_requirement_index",
                return_value=RequirementIndex(),
            ),
            patch(
                "learn_to_cloud.services.progress_service.get_curriculum_catalog",
                return_value=fake_catalog,
            ),
            patch(
                "learn_to_cloud.services.progress_service.resolve_completed_step_uuids",
                new=AsyncMock(return_value={current_step_uuid, stale_step_uuid}),
            ),
            patch(
                "learn_to_cloud.services.progress_service.resolve_succeeded_requirement_uuids",
                new=AsyncMock(return_value={current_req_uuid, stale_req_uuid}),
            ),
        ):
            result = await fetch_user_progress(AsyncMock(), user_id=1)

        # Only UUIDs mapped by the catalog count toward a phase; stale
        # step/requirement UUIDs (not in phase_order_by_*_uuid) drop out.
        assert result.phases[0].learning.steps_completed == 1
        assert result.phases[1].verification.requirements_verified == 1


# ---------------------------------------------------------------------------
# fetch_phase_progress
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestFetchPhaseProgress:
    @pytest.mark.asyncio
    async def test_queries_db(self):
        topic = _make_topic(steps=["s1", "s2"])
        phase = _make_phase(0, topics=[topic])
        completed_uuids = {s.uuid for s in topic.learning_steps}

        with patch(
            "learn_to_cloud.services.progress_service.resolve_completed_step_uuids",
            new=AsyncMock(return_value=completed_uuids),
        ):
            result = await fetch_phase_progress(AsyncMock(), user_id=1, phase=phase)

        assert result.learning.steps_completed == 2
        assert result.learning.percentage == 100.0
        # No hands-on verification configured -> verification-complete by
        # definition, so the phase is fully complete.
        assert result.is_complete is True

    @pytest.mark.asyncio
    async def test_not_complete_when_verification_pending(self):
        """All steps done but verification pending must not be complete."""
        from learn_to_cloud_shared.schemas import PhaseHandsOnVerificationOverview
        from learn_to_cloud_shared.testing.requirement_factories import (
            journal_api_verifier_requirement,
        )

        topic = _make_topic(topic_id="phase3-topic1", steps=["s1", "s2"])
        req = journal_api_verifier_requirement(slug="req1", name="R", description="d")
        phase = _make_phase(3, topics=[topic])
        phase = phase.model_copy(
            update={
                "hands_on_verification": PhaseHandsOnVerificationOverview(
                    requirements=[req],
                ),
            }
        )
        completed_uuids = {s.uuid for s in topic.learning_steps}

        with (
            patch(
                "learn_to_cloud.services.progress_service.resolve_completed_step_uuids",
                new=AsyncMock(return_value=completed_uuids),
            ),
            patch(
                "learn_to_cloud.services.progress_service.resolve_succeeded_requirement_uuids",
                new=AsyncMock(return_value=set()),
            ),
        ):
            result = await fetch_phase_progress(AsyncMock(), user_id=1, phase=phase)

        assert result.learning.steps_completed == 2
        assert result.learning.is_complete is True
        assert result.verification.requirements_verified == 0
        assert result.verification.requirements_required == 1
        assert result.verification.is_complete is False
        assert result.is_complete is False

    @pytest.mark.asyncio
    async def test_is_complete_when_all_done(self):
        """All steps and verification done means both-measures complete."""
        from learn_to_cloud_shared.schemas import PhaseHandsOnVerificationOverview
        from learn_to_cloud_shared.testing.requirement_factories import (
            journal_api_verifier_requirement,
        )

        topic = _make_topic(topic_id="phase3-topic1", steps=["s1", "s2"])
        req = journal_api_verifier_requirement(slug="req1", name="R", description="d")
        phase = _make_phase(3, topics=[topic])
        phase = phase.model_copy(
            update={
                "hands_on_verification": PhaseHandsOnVerificationOverview(
                    requirements=[req],
                ),
            }
        )
        completed_uuids = {s.uuid for s in topic.learning_steps}

        with (
            patch(
                "learn_to_cloud.services.progress_service.resolve_completed_step_uuids",
                new=AsyncMock(return_value=completed_uuids),
            ),
            patch(
                "learn_to_cloud.services.progress_service.resolve_succeeded_requirement_uuids",
                new=AsyncMock(return_value={req.uuid}),
            ),
        ):
            result = await fetch_phase_progress(AsyncMock(), user_id=1, phase=phase)

        assert result.learning.steps_completed == 2
        assert result.verification.requirements_verified == 1
        assert result.verification.requirements_required == 1
        assert result.is_complete is True

    @pytest.mark.asyncio
    async def test_zero_requirement_phase_is_verification_complete(self):
        """A phase with no hands-on verification never blocks on it."""
        topic = _make_topic(steps=["s1"])
        phase = _make_phase(0, topics=[topic])

        with patch(
            "learn_to_cloud.services.progress_service.resolve_completed_step_uuids",
            new=AsyncMock(return_value=set()),
        ):
            result = await fetch_phase_progress(AsyncMock(), user_id=1, phase=phase)

        assert result.verification.requirements_required == 0
        assert result.verification.is_complete is True
        # Learning still pending -> phase overall not complete.
        assert result.learning.is_complete is False
        assert result.is_complete is False


# ---------------------------------------------------------------------------
# find_first_incomplete_step / resolve_continue_destination
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestFindFirstIncompleteStep:
    def test_returns_first_unchecked_step_in_topic_order(self):
        first_topic = _make_topic("t1", steps=["s1", "s2"])
        second_topic = _make_topic("t2", steps=["s3"])
        phase = _make_phase(0, topics=[first_topic, second_topic])
        completed = {first_topic.learning_steps[0].uuid}

        result = find_first_incomplete_step(phase, completed)

        assert result is not None
        topic, step = result
        assert topic.slug == first_topic.slug
        assert step.slug == "s2"

    def test_returns_none_when_every_step_checked(self):
        topic = _make_topic("t1", steps=["s1", "s2"])
        phase = _make_phase(0, topics=[topic])
        completed = {s.uuid for s in topic.learning_steps}

        assert find_first_incomplete_step(phase, completed) is None

    def test_returns_none_for_a_phase_with_no_steps(self):
        phase = _make_phase(0, topics=[])
        assert find_first_incomplete_step(phase, set()) is None


@pytest.mark.unit
class TestResolveContinueDestination:
    @pytest.mark.asyncio
    async def test_links_to_first_incomplete_steps_topic(self):
        topic = _make_topic("t1", steps=["s1", "s2"])
        phase = _make_phase(3, topics=[topic])

        with patch(
            "learn_to_cloud.services.progress_service.resolve_completed_step_uuids",
            new=AsyncMock(return_value=set()),
        ):
            destination = await resolve_continue_destination(
                AsyncMock(), user_id=1, phase=phase
            )

        assert destination == "/phase/3/topic1"

    @pytest.mark.asyncio
    async def test_falls_back_to_verification_section_when_all_steps_checked(self):
        topic = _make_topic("t1", steps=["s1"])
        phase = _with_requirement(_make_phase(3, topics=[topic]))
        completed = {s.uuid for s in topic.learning_steps}

        with patch(
            "learn_to_cloud.services.progress_service.resolve_completed_step_uuids",
            new=AsyncMock(return_value=completed),
        ):
            destination = await resolve_continue_destination(
                AsyncMock(), user_id=1, phase=phase
            )

        assert destination == "/phase/3#verification-section"

    @pytest.mark.asyncio
    async def test_hands_on_only_phase_links_straight_to_verification(self):
        """A zero-step phase has nothing to check off, so it goes straight
        to verification without ever calling the DB."""
        phase = _with_requirement(_make_phase(3, topics=[]))

        with patch(
            "learn_to_cloud.services.progress_service.resolve_completed_step_uuids",
            new=AsyncMock(return_value=set()),
        ) as mock_resolve:
            destination = await resolve_continue_destination(
                AsyncMock(), user_id=1, phase=phase
            )

        assert destination == "/phase/3#verification-section"
        mock_resolve.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_phase_without_requirements_does_not_link_dead_anchor(self):
        phase = _make_phase(3, topics=[])

        with patch(
            "learn_to_cloud.services.progress_service.resolve_completed_step_uuids",
            new=AsyncMock(return_value=set()),
        ):
            destination = await resolve_continue_destination(
                AsyncMock(), user_id=1, phase=phase
            )

        assert destination == "/phase/3"
