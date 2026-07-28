"""Unit tests for rendering.context module.

Tests cover:
- build_progress_dict percentage calculation
- build_phase_topics merges topics with progress
- build_topic_nav prev/next navigation
- build_requirement_card_context card_state derivation
"""

from uuid import uuid4

import pytest
from learn_to_cloud_shared.models import SubmissionType
from learn_to_cloud_shared.schemas import (
    HandsOnRequirement,
    LearningProgress,
    LearningStep,
    Phase,
    PhaseProgress,
    Topic,
    TopicProgressData,
    VerificationProgress,
)

from learn_to_cloud.rendering.context import (
    build_phase_topics,
    build_progress_dict,
    build_requirement_card_context,
    build_topic_nav,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_topic(topic_id: str, slug: str, name: str = "") -> Topic:
    return Topic(
        uuid=uuid4(),
        slug=slug,
        name=name or slug,
        description="",
        order=0,
        learning_steps=[LearningStep(uuid=uuid4(), slug="s1", order=0)],
    )


# ---------------------------------------------------------------------------
# build_progress_dict
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestBuildProgressDict:
    def test_basic(self):
        result = build_progress_dict(3, 10)
        assert result == {"completed": 3, "total": 10, "percentage": 30}

    def test_zero_total(self):
        result = build_progress_dict(0, 0)
        assert result["percentage"] == 0


# ---------------------------------------------------------------------------
# build_phase_topics
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestBuildPhaseTopics:
    def test_merges_topics_with_progress(self):
        topic = _make_topic("phase0-t1", "basics", "Basics")
        phase = Phase(
            uuid=uuid4(),
            name="P0",
            slug="phase0",
            order=0,
            topics=[topic],
        )
        detail = PhaseProgress(
            phase_id=0,
            learning=LearningProgress(steps_completed=1, steps_required=3),
            verification=VerificationProgress(
                requirements_verified=0, requirements_required=0
            ),
            topic_progress={
                topic.uuid: TopicProgressData(
                    steps_completed=1,
                    steps_total=3,
                    percentage=33.3,
                    status="in_progress",
                ),
            },
        )
        topics = build_phase_topics(phase, detail)
        assert len(topics) == 1
        assert topics[0]["name"] == "Basics"
        assert topics[0]["slug"] == "basics"
        assert topics[0]["progress"]["completed"] == 1

    def test_topic_without_progress(self):
        topic = _make_topic("phase0-t1", "basics")
        phase = Phase(
            uuid=uuid4(),
            name="P0",
            slug="phase0",
            order=0,
            topics=[topic],
        )
        detail = PhaseProgress(
            phase_id=0,
            learning=LearningProgress(steps_completed=0, steps_required=3),
            verification=VerificationProgress(
                requirements_verified=0, requirements_required=0
            ),
            topic_progress={},
        )
        topics = build_phase_topics(phase, detail)
        assert topics[0]["progress"] is None

    def test_topic_order_matches_phase_topic_order(self):
        first = _make_topic("phase0-t1", "first", "First")
        second = _make_topic("phase0-t2", "second", "Second")
        phase = Phase(
            uuid=uuid4(),
            name="P0",
            slug="phase0",
            order=0,
            topics=[first, second],
        )
        detail = PhaseProgress(
            phase_id=0,
            learning=LearningProgress(steps_completed=1, steps_required=6),
            verification=VerificationProgress(
                requirements_verified=0, requirements_required=0
            ),
            topic_progress={},
        )
        topics = build_phase_topics(phase, detail)
        assert [t["slug"] for t in topics] == ["first", "second"]


# ---------------------------------------------------------------------------
# build_topic_nav
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestBuildTopicNav:
    def _topics(self) -> list[Topic]:
        return [
            _make_topic("t1", "first", "First"),
            _make_topic("t2", "second", "Second"),
            _make_topic("t3", "third", "Third"),
        ]

    def test_middle_topic(self):
        prev_t, next_t = build_topic_nav(self._topics(), "second", 0, "Phase 0")
        assert prev_t is not None
        assert prev_t["slug"] == "first"
        assert next_t is not None
        assert next_t["slug"] == "third"

    def test_first_topic_prev_is_phase_link(self):
        prev_t, next_t = build_topic_nav(self._topics(), "first", 0, "Phase 0")
        assert prev_t is not None
        assert prev_t["slug"] is None
        assert prev_t["url"] == "/phase/0"
        assert next_t is not None
        assert next_t["slug"] == "second"

    def test_last_topic_next_is_phase_link(self):
        prev_t, next_t = build_topic_nav(self._topics(), "third", 0, "Phase 0")
        assert prev_t is not None
        assert prev_t["slug"] == "second"
        assert next_t is not None
        assert next_t["slug"] is None
        assert next_t["url"] == "/phase/0"

    def test_unknown_slug_returns_none(self):
        prev_t, next_t = build_topic_nav(self._topics(), "nonexistent", 0, "Phase 0")
        assert prev_t is None
        assert next_t is None

    def test_single_topic(self):
        topics = [_make_topic("t1", "only", "Only")]
        prev_t, next_t = build_topic_nav(topics, "only", 0, "Phase 0")
        assert prev_t is not None
        assert prev_t["url"] == "/phase/0"
        assert next_t is not None
        assert next_t["url"] == "/phase/0"


# ---------------------------------------------------------------------------
# build_requirement_card_context
# ---------------------------------------------------------------------------


def _make_requirement(
    submission_type: SubmissionType,
    required_repo: str | None = None,
) -> HandsOnRequirement:
    from learn_to_cloud_shared.testing.requirement_factories import make_requirement

    return make_requirement(
        submission_type,
        slug="req-1",
        name="Test",
        description="Test",
        required_repo=required_repo,
    )


@pytest.mark.unit
class TestBuildRequirementCardContext:
    def test_derivable_profile_readme_populates_derived_url(self):
        req = _make_requirement(SubmissionType.PROFILE_README)
        ctx = build_requirement_card_context(
            requirement=req,
            github_username="alice",
        )
        assert ctx["derived_url"] == "https://github.com/alice/alice"

    def test_derivable_journal_api_verifier_uses_required_repo(self):
        req = _make_requirement(
            SubmissionType.JOURNAL_API_VERIFIER,
            required_repo="learntocloud/journal-starter",
        )
        ctx = build_requirement_card_context(
            requirement=req,
            github_username="bob",
        )
        assert ctx["derived_url"] == "https://github.com/bob/journal-starter"

    def test_token_type_has_no_derived_url_or_prefix(self):
        req = _make_requirement(SubmissionType.CTF_TOKEN)
        ctx = build_requirement_card_context(
            requirement=req,
            github_username="alice",
        )
        assert ctx["derived_url"] is None

    def test_misconfigured_required_repo_falls_back_to_none(self):
        """JOURNAL_API_VERIFIER without required_repo is now impossible (#470).

        After hoisting requirements into per-type subclasses, the Pydantic
        schema rejects construction of a JournalApiVerifierRequirement
        without required_repo. The defensive try/except in
        build_requirement_card_context still exists as defense in depth
        but is unreachable through normal construction.
        """
        from learn_to_cloud_shared.schemas import HandsOnRequirementAdapter
        from pydantic import ValidationError

        # Construct via TypeAdapter with raw dict so static analysis
        # doesn't catch the deliberate validation error.
        with pytest.raises(ValidationError):
            HandsOnRequirementAdapter.validate_python(
                {
                    "uuid": "00000000-0000-0000-0000-000000000001",
                    "id": "journal",
                    "submission_type": "journal_api_verifier",
                    "name": "Test",
                    "description": "Test",
                    "type_config": {},
                }
            )


# ---------------------------------------------------------------------------
# build_requirement_card_context — card_state derivation
# ---------------------------------------------------------------------------


def _make_submission(
    *,
    is_validated: bool,
    verification_completed: bool = False,
    validation_message: str | None = None,
):
    from datetime import UTC, datetime

    from learn_to_cloud_shared.schemas import SubmissionData

    return SubmissionData(
        id=uuid4(),
        submitted_value="https://github.com/alice/repo",
        is_validated=is_validated,
        verification_completed=verification_completed,
        validation_message=validation_message,
        created_at=datetime(2024, 1, 1, tzinfo=UTC),
    )


@pytest.mark.unit
class TestBuildRequirementCardContextCardState:
    def test_processing_is_checking_regardless_of_submission(self):
        req = _make_requirement(SubmissionType.CTF_TOKEN)
        ctx = build_requirement_card_context(
            requirement=req, github_username="alice", processing=True
        )
        assert ctx["card_state"] == "checking"

    def test_no_submission_is_not_started(self):
        req = _make_requirement(SubmissionType.CTF_TOKEN)
        ctx = build_requirement_card_context(requirement=req, github_username="alice")
        assert ctx["card_state"] == "not_started"
        assert ctx["error_banner"] is None

    def test_validated_submission_is_passed(self):
        req = _make_requirement(SubmissionType.CTF_TOKEN)
        submission = _make_submission(is_validated=True, verification_completed=True)
        ctx = build_requirement_card_context(
            requirement=req, github_username="alice", submission=submission
        )
        assert ctx["card_state"] == "passed"

    def test_learner_failure_is_failed_with_validation_message(self):
        req = _make_requirement(SubmissionType.CTF_TOKEN)
        submission = _make_submission(
            is_validated=False,
            verification_completed=True,
            validation_message="Token did not match.",
        )
        ctx = build_requirement_card_context(
            requirement=req, github_username="alice", submission=submission
        )
        assert ctx["card_state"] == "failed"
        assert ctx["error_banner"] == "Token did not match."
        assert ctx["server_error"] is False

    def test_persisted_system_fault_is_unavailable_not_failed(self):
        """A terminal server_error/cancelled outcome, read back from storage.

        Regression: previously the phase page hardcoded ``server_error=False``
        for every persisted card, so this state rendered identically to a
        real learner failure.
        """
        req = _make_requirement(SubmissionType.CTF_TOKEN)
        submission = _make_submission(is_validated=False, verification_completed=False)
        ctx = build_requirement_card_context(
            requirement=req, github_username="alice", submission=submission
        )
        assert ctx["card_state"] == "unavailable"
        assert ctx["server_error"] is True
        assert ctx["server_error_message"]
        # No red inline banner text -- the amber service banner covers it.
        assert ctx["error_banner"] is None

    def test_explicit_server_error_overrides_missing_submission(self):
        """The live submit/poll flow can force 'unavailable' with no row yet."""
        req = _make_requirement(SubmissionType.CTF_TOKEN)
        ctx = build_requirement_card_context(
            requirement=req,
            github_username="alice",
            server_error=True,
            server_error_message="Verification could not be started.",
            server_error_retryable=False,
        )
        assert ctx["card_state"] == "unavailable"
        assert ctx["server_error_message"] == "Verification could not be started."
        assert ctx["server_error_retryable"] is False
