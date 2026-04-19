"""Unit tests for rendering.context module.

Tests cover:
- build_progress_dict percentage calculation
- build_feedback_tasks_from_results object conversion
- build_phase_topics merges topics with progress
- build_topic_nav prev/next navigation
"""

import pytest

from models import SubmissionType
from rendering.context import (
    build_feedback_tasks_from_results,
    build_phase_topics,
    build_progress_dict,
    build_requirement_card_context,
    build_topic_nav,
)
from schemas import (
    HandsOnRequirement,
    LearningStep,
    Phase,
    PhaseProgress,
    TaskResult,
    Topic,
    TopicProgressData,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_topic(topic_id: str, slug: str, name: str = "") -> Topic:
    return Topic(
        id=topic_id,
        slug=slug,
        name=name or slug,
        description="",
        order=0,
        learning_steps=[LearningStep(id="s1", order=0)],
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
# build_feedback_tasks_from_results
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestBuildFeedbackTasksFromResults:
    def test_with_results(self):
        results = [
            TaskResult(task_name="Task A", passed=True, feedback="Good"),
            TaskResult(task_name="Task B", passed=False, feedback="Fix this"),
        ]
        tasks, passed = build_feedback_tasks_from_results(results)
        assert len(tasks) == 2
        assert passed == 1
        assert tasks[0]["name"] == "Task A"
        assert tasks[1]["message"] == "Fix this"

    def test_none_input(self):
        tasks, passed = build_feedback_tasks_from_results(None)
        assert tasks == []
        assert passed == 0

    def test_empty_list(self):
        tasks, passed = build_feedback_tasks_from_results([])
        assert tasks == []
        assert passed == 0


# ---------------------------------------------------------------------------
# build_phase_topics
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestBuildPhaseTopics:
    def test_merges_topics_with_progress(self):
        topic = _make_topic("phase0-t1", "basics", "Basics")
        phase = Phase(
            id=0,
            name="P0",
            slug="phase0",
            order=0,
            topics=[topic],
        )
        detail = PhaseProgress(
            phase_id=0,
            steps_completed=1,
            steps_required=3,
            hands_on_validated=0,
            hands_on_required=0,
            topic_progress={
                "phase0-t1": TopicProgressData(
                    steps_completed=1,
                    steps_total=3,
                    percentage=33.3,
                    status="in_progress",
                ),
            },
        )
        topics, progress = build_phase_topics(phase, detail)
        assert len(topics) == 1
        assert topics[0]["name"] == "Basics"
        assert topics[0]["slug"] == "basics"
        assert topics[0]["progress"]["completed"] == 1
        assert progress["percentage"] == pytest.approx(33.3, abs=0.1)
        assert progress["is_complete"] is False

    def test_topic_without_progress(self):
        topic = _make_topic("phase0-t1", "basics")
        phase = Phase(id=0, name="P0", slug="phase0", order=0, topics=[topic])
        detail = PhaseProgress(
            phase_id=0,
            steps_completed=0,
            steps_required=3,
            hands_on_validated=0,
            hands_on_required=0,
            topic_progress={},
        )
        topics, _ = build_phase_topics(phase, detail)
        assert topics[0]["progress"] is None

    def test_progress_is_complete_when_all_done(self):
        topic = _make_topic("phase0-t1", "basics", "Basics")
        phase = Phase(
            id=0,
            name="P0",
            slug="phase0",
            order=0,
            topics=[topic],
        )
        detail = PhaseProgress(
            phase_id=0,
            steps_completed=3,
            steps_required=3,
            hands_on_validated=1,
            hands_on_required=1,
            topic_progress={
                "phase0-t1": TopicProgressData(
                    steps_completed=3,
                    steps_total=3,
                    percentage=100.0,
                    status="completed",
                ),
            },
        )
        _, progress = build_phase_topics(phase, detail)
        assert progress["percentage"] == 100
        assert progress["is_complete"] is True


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
    return HandsOnRequirement(
        id="req-1",
        submission_type=submission_type,
        name="Test",
        description="Test",
        required_repo=required_repo,
    )


@pytest.mark.unit
class TestBuildRequirementCardContext:
    def test_derivable_github_profile_populates_derived_url(self):
        req = _make_requirement(SubmissionType.GITHUB_PROFILE)
        ctx = build_requirement_card_context(
            requirement=req,
            github_username="alice",
        )
        assert ctx["derived_url"] == "https://github.com/alice"
        assert ctx["pr_url_prefix"] is None

    def test_derivable_ci_status_uses_required_repo(self):
        req = _make_requirement(
            SubmissionType.CI_STATUS,
            required_repo="learntocloud/journal-starter",
        )
        ctx = build_requirement_card_context(
            requirement=req,
            github_username="bob",
        )
        assert ctx["derived_url"] == "https://github.com/bob/journal-starter"

    def test_pr_review_populates_pr_url_prefix(self):
        req = _make_requirement(
            SubmissionType.PR_REVIEW,
            required_repo="learntocloud/journal-starter",
        )
        ctx = build_requirement_card_context(
            requirement=req,
            github_username="carol",
        )
        assert ctx["derived_url"] is None
        assert ctx["pr_url_prefix"] == (
            "https://github.com/carol/journal-starter/pull/"
        )

    def test_token_type_has_no_derived_url_or_prefix(self):
        req = _make_requirement(SubmissionType.CTF_TOKEN)
        ctx = build_requirement_card_context(
            requirement=req,
            github_username="alice",
        )
        assert ctx["derived_url"] is None
        assert ctx["pr_url_prefix"] is None

    def test_misconfigured_required_repo_falls_back_to_none(self):
        # CI_STATUS without required_repo would raise inside derive,
        # but the builder should swallow that and return None so the
        # template can show its error state.
        req = _make_requirement(SubmissionType.CI_STATUS)
        ctx = build_requirement_card_context(
            requirement=req,
            github_username="alice",
        )
        assert ctx["derived_url"] is None
