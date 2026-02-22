"""Unit tests for rendering.context module.

Tests cover:
- build_progress_dict percentage calculation
- build_feedback_tasks JSON parsing and counting
- build_feedback_tasks_from_results object conversion
- build_phase_topics merges topics with progress
- build_topic_nav prev/next navigation
"""

import pytest

from rendering.context import (
    build_feedback_tasks,
    build_feedback_tasks_from_results,
    build_phase_topics,
    build_progress_dict,
    build_topic_nav,
)
from schemas import (
    LearningStep,
    Phase,
    PhaseDetailProgress,
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

    def test_full(self):
        result = build_progress_dict(5, 5)
        assert result["percentage"] == 100


# ---------------------------------------------------------------------------
# build_feedback_tasks
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestBuildFeedbackTasks:
    def test_valid_json(self):
        json_str = (
            '[{"task_name":"A","passed":true,"feedback":"ok"},'
            '{"task_name":"B","passed":false,"feedback":"nope"}]'
        )
        tasks, passed = build_feedback_tasks(json_str)
        assert len(tasks) == 2
        assert passed == 1
        assert tasks[0]["name"] == "A"
        assert tasks[0]["passed"] is True
        assert tasks[1]["message"] == "nope"

    def test_none_input(self):
        tasks, passed = build_feedback_tasks(None)
        assert tasks == []
        assert passed == 0

    def test_empty_string(self):
        tasks, passed = build_feedback_tasks("")
        assert tasks == []
        assert passed == 0

    def test_invalid_json(self):
        tasks, passed = build_feedback_tasks("not json")
        assert tasks == []
        assert passed == 0

    def test_all_passed(self):
        json_str = (
            '[{"task_name":"A","passed":true,"feedback":""},'
            '{"task_name":"B","passed":true,"feedback":""}]'
        )
        _, passed = build_feedback_tasks(json_str)
        assert passed == 2

    def test_missing_fields_use_defaults(self):
        json_str = "[{}]"
        tasks, passed = build_feedback_tasks(json_str)
        assert tasks[0]["name"] == ""
        assert tasks[0]["passed"] is False
        assert tasks[0]["message"] == ""
        assert passed == 0


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
        detail = PhaseDetailProgress(
            topic_progress={
                "phase0-t1": TopicProgressData(
                    steps_completed=1,
                    steps_total=3,
                    percentage=33.3,
                    status="in_progress",
                ),
            },
            steps_completed=1,
            steps_total=3,
            percentage=33,
        )
        topics, progress = build_phase_topics(phase, detail)
        assert len(topics) == 1
        assert topics[0]["name"] == "Basics"
        assert topics[0]["slug"] == "basics"
        assert topics[0]["progress"]["completed"] == 1
        assert progress["percentage"] == 33

    def test_topic_without_progress(self):
        topic = _make_topic("phase0-t1", "basics")
        phase = Phase(id=0, name="P0", slug="phase0", order=0, topics=[topic])
        detail = PhaseDetailProgress(
            topic_progress={},
            steps_completed=0,
            steps_total=3,
            percentage=0,
        )
        topics, _ = build_phase_topics(phase, detail)
        assert topics[0]["progress"] is None


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
