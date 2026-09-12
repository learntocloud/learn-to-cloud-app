"""Topic navigation boundaries."""

from uuid import uuid4

import pytest
from learn_to_cloud_shared.schemas import LearningStep, Topic

from learn_to_cloud.rendering.topic_navigation import build_topic_nav


@pytest.mark.unit
class TestBuildTopicNav:
    def _topics(self) -> list[Topic]:
        return [
            Topic(
                uuid=uuid4(),
                slug=slug,
                name=name,
                description="",
                order=order,
                learning_steps=[LearningStep(uuid=uuid4(), slug="s1", order=0)],
            )
            for order, (slug, name) in enumerate(
                [("first", "First"), ("second", "Second"), ("third", "Third")]
            )
        ]

    def test_middle_topic(self):
        prev_t, next_t = build_topic_nav(self._topics(), "second", 0, "Phase 0")
        assert prev_t == {"name": "First", "url": "/phase/0/first"}
        assert next_t == {"name": "Third", "url": "/phase/0/third"}

    def test_first_topic_prev_is_phase_link(self):
        prev_t, next_t = build_topic_nav(self._topics(), "first", 0, "Phase 0")
        assert prev_t == {"name": "Phase 0", "url": "/phase/0"}
        assert next_t == {"name": "Second", "url": "/phase/0/second"}

    def test_last_topic_next_is_phase_link(self):
        prev_t, next_t = build_topic_nav(self._topics(), "third", 0, "Phase 0")
        assert prev_t == {"name": "Second", "url": "/phase/0/second"}
        assert next_t == {"name": "Phase 0", "url": "/phase/0"}

    def test_last_topic_continues_to_verification_when_available(self):
        prev_t, next_t = build_topic_nav(
            self._topics(),
            "third",
            1,
            "Linux and Bash",
            has_verification=True,
        )

        assert prev_t == {"name": "Second", "url": "/phase/1/second"}
        assert next_t == {
            "label": "Next step",
            "name": "Continue to Phase 1 verification",
            "url": "/verifications/phase/1",
        }

    def test_unknown_slug_returns_none(self):
        prev_t, next_t = build_topic_nav(self._topics(), "nonexistent", 0, "Phase 0")
        assert prev_t is None
        assert next_t is None

    def test_single_topic(self):
        topics = self._topics()[:1]
        prev_t, next_t = build_topic_nav(topics, "first", 0, "Phase 0")
        assert prev_t is not None
        assert prev_t["url"] == "/phase/0"
        assert next_t is not None
        assert next_t["url"] == "/phase/0"

    def test_empty_topics(self):
        assert build_topic_nav([], "missing", 0, "Phase 0") == (None, None)
