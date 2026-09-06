"""Learning-progress template data."""

from uuid import uuid4

import pytest
from learn_to_cloud_shared.schemas import (
    LearningProgress,
    LearningStep,
    Phase,
    PhaseProgress,
    Topic,
    TopicProgressData,
    VerificationProgress,
)

from learn_to_cloud.rendering.progress import build_phase_topics, build_progress_dict


def _make_topic(slug: str, name: str = "") -> Topic:
    return Topic(
        uuid=uuid4(),
        slug=slug,
        name=name or slug,
        description="",
        order=0,
        learning_steps=[LearningStep(uuid=uuid4(), slug="s1", order=0)],
    )


@pytest.mark.unit
class TestBuildProgressDict:
    def test_basic(self):
        result = build_progress_dict(3, 10)
        assert result == {"completed": 3, "total": 10, "percentage": 30}

    def test_zero_total(self):
        result = build_progress_dict(0, 0)
        assert result["percentage"] == 0


@pytest.mark.unit
class TestBuildPhaseTopics:
    def test_merges_topics_with_progress(self):
        topic = _make_topic("basics", "Basics")
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
        topic = _make_topic("basics")
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
        first = _make_topic("first", "First")
        second = _make_topic("second", "Second")
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
