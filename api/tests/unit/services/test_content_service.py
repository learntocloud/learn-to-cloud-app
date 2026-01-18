"""Tests for services/content_service.py - content loading and caching."""

import json
from unittest.mock import patch

import pytest

from services.content_service import (
    LearningObjective,
    LearningStep,
    Phase,
    PhaseCapstoneOverview,
    PhaseHandsOnVerificationOverview,
    ProviderOption,
    Question,
    SecondaryLink,
    Topic,
    _load_phase,
    _load_topic,
    clear_cache,
    get_all_phases,
    get_phase_by_id,
    get_phase_by_slug,
    get_phase_for_topic,
    get_topic_by_id,
    get_topic_by_slugs,
)


@pytest.fixture(autouse=True)
def clear_content_cache():
    """Clear cache before each test."""
    clear_cache()
    yield
    clear_cache()


class TestDataclasses:
    """Test that dataclasses are properly defined."""

    def test_secondary_link(self):
        link = SecondaryLink(text="Docs", url="https://example.com")
        assert link.text == "Docs"
        assert link.url == "https://example.com"

    def test_provider_option(self):
        opt = ProviderOption(
            provider="azure",
            title="Azure Guide",
            url="https://azure.com",
            description="Azure-specific steps",
        )
        assert opt.provider == "azure"
        assert opt.title == "Azure Guide"
        assert opt.description == "Azure-specific steps"

    def test_provider_option_default_description(self):
        opt = ProviderOption(provider="aws", title="AWS", url="https://aws.com")
        assert opt.description is None

    def test_learning_step(self):
        step = LearningStep(
            order=1,
            text="Read the documentation",
            action="read",
            title="Getting Started",
            url="https://docs.example.com",
        )
        assert step.order == 1
        assert step.action == "read"
        assert step.secondary_links == ()
        assert step.options == ()

    def test_learning_step_with_links_and_options(self):
        step = LearningStep(
            order=1,
            text="Learn basics",
            secondary_links=(SecondaryLink("More", "https://more.com"),),
            options=(ProviderOption("gcp", "GCP", "https://gcp.com"),),
        )
        assert len(step.secondary_links) == 1
        assert len(step.options) == 1

    def test_question(self):
        q = Question(
            id="q1",
            prompt="What is the cloud?",
        )
        assert q.id == "q1"
        assert q.prompt == "What is the cloud?"

    def test_learning_objective(self):
        obj = LearningObjective(id="obj1", text="Understand cloud basics", order=1)
        assert obj.id == "obj1"
        assert obj.order == 1

    def test_topic(self):
        topic = Topic(
            id="phase0-topic1",
            slug="intro",
            name="Introduction",
            description="Getting started",
            order=1,
            estimated_time="30 mins",
            is_capstone=False,
            learning_steps=(),
            questions=(),
        )
        assert topic.id == "phase0-topic1"
        assert topic.is_capstone is False
        assert topic.learning_objectives == ()

    def test_phase_capstone_overview(self):
        capstone = PhaseCapstoneOverview(
            title="Build a Project",
            summary="Apply your knowledge",
            includes=("Design", "Implementation"),
            topic_slug="capstone",
        )
        assert capstone.title == "Build a Project"
        assert len(capstone.includes) == 2

    def test_phase_hands_on_verification(self):
        hov = PhaseHandsOnVerificationOverview(
            summary="Verify your skills",
            includes=("GitHub repo", "Live demo"),
        )
        assert "Verify" in hov.summary

    def test_phase(self):
        phase = Phase(
            id=0,
            name="Phase 0",
            slug="phase0",
            description="The beginning",
            short_description="Start here",
            estimated_weeks="2-3",
            order=0,
            objectives=("Learn basics",),
            capstone=None,
            hands_on_verification=None,
            topic_slugs=("intro",),
            topics=(),
        )
        assert phase.id == 0
        assert phase.slug == "phase0"


class TestGetAllPhases:
    """Test get_all_phases function with real content."""

    def test_returns_phases(self):
        """Real content directory has phases."""
        phases = get_all_phases()
        assert len(phases) >= 1  # At least phase 0 exists

    def test_phases_are_sorted_by_order(self):
        """Phases are returned in order."""
        phases = get_all_phases()
        orders = [p.order for p in phases]
        assert orders == sorted(orders)

    def test_caching_works(self):
        """Repeated calls return same cached result."""
        phases1 = get_all_phases()
        phases2 = get_all_phases()
        assert phases1 is phases2  # Same object (cached)

    def test_phase_zero_exists(self):
        """Phase 0 is always present."""
        phases = get_all_phases()
        phase_ids = [p.id for p in phases]
        assert 0 in phase_ids


class TestGetPhaseById:
    """Test get_phase_by_id function."""

    def test_existing_phase(self):
        """Returns phase when it exists."""
        phase = get_phase_by_id(0)
        assert phase is not None
        assert phase.id == 0

    def test_nonexistent_phase(self):
        """Returns None for invalid ID."""
        phase = get_phase_by_id(999)
        assert phase is None


class TestGetPhaseBySlug:
    """Test get_phase_by_slug function."""

    def test_existing_phase(self):
        """Returns phase when slug matches."""
        phase = get_phase_by_slug("phase0")
        assert phase is not None
        assert phase.slug == "phase0"

    def test_nonexistent_slug(self):
        """Returns None for invalid slug."""
        phase = get_phase_by_slug("nonexistent")
        assert phase is None


class TestGetTopicById:
    """Test get_topic_by_id function."""

    def test_existing_topic(self):
        """Returns topic when it exists."""
        # Get a real topic ID from phase 0
        phase = get_phase_by_id(0)
        if phase and phase.topics:
            topic_id = phase.topics[0].id
            topic = get_topic_by_id(topic_id)
            assert topic is not None
            assert topic.id == topic_id

    def test_nonexistent_topic(self):
        """Returns None for invalid topic ID."""
        topic = get_topic_by_id("nonexistent-topic")
        assert topic is None


class TestGetTopicBySlugs:
    """Test get_topic_by_slugs function."""

    def test_existing_topic(self):
        """Returns topic when phase and topic slugs match."""
        phase = get_phase_by_slug("phase0")
        if phase and phase.topics:
            topic_slug = phase.topics[0].slug
            topic = get_topic_by_slugs("phase0", topic_slug)
            assert topic is not None
            assert topic.slug == topic_slug

    def test_invalid_phase_slug(self):
        """Returns None when phase doesn't exist."""
        topic = get_topic_by_slugs("nonexistent", "topic1")
        assert topic is None

    def test_invalid_topic_slug(self):
        """Returns None when topic doesn't exist in phase."""
        topic = get_topic_by_slugs("phase0", "nonexistent-topic")
        assert topic is None


class TestGetPhaseForTopic:
    """Test get_phase_for_topic function."""

    def test_finds_phase(self):
        """Returns the phase containing the topic."""
        phase = get_phase_by_id(0)
        if phase and phase.topics:
            topic_id = phase.topics[0].id
            found_phase = get_phase_for_topic(topic_id)
            assert found_phase is not None
            assert found_phase.id == phase.id

    def test_nonexistent_topic(self):
        """Returns None for unknown topic."""
        phase = get_phase_for_topic("nonexistent-topic")
        assert phase is None


class TestClearCache:
    """Test cache clearing."""

    def test_clear_cache_reloads(self):
        """Clearing cache causes content to reload."""
        phases1 = get_all_phases()
        clear_cache()
        phases2 = get_all_phases()
        # After clear, should be new objects (reloaded)
        # Note: content is same, but tuple is rebuilt
        assert phases1 is not phases2


class TestLoadTopicWithMockedFiles:
    """Test _load_topic with mocked file system."""

    def test_topic_file_not_found(self, tmp_path):
        """Returns None when topic file doesn't exist."""
        topic = _load_topic(tmp_path, "nonexistent")
        assert topic is None

    def test_invalid_json(self, tmp_path):
        """Returns None on invalid JSON."""
        topic_file = tmp_path / "bad.json"
        topic_file.write_text("not valid json")
        topic = _load_topic(tmp_path, "bad")
        assert topic is None

    def test_missing_required_fields(self, tmp_path):
        """Returns None when required fields missing."""
        topic_file = tmp_path / "incomplete.json"
        topic_file.write_text(json.dumps({"name": "Test"}))  # Missing id, slug
        topic = _load_topic(tmp_path, "incomplete")
        assert topic is None

    def test_valid_minimal_topic(self, tmp_path):
        """Loads topic with minimal required fields."""
        topic_data = {
            "id": "test-topic",
            "slug": "test",
            "name": "Test Topic",
        }
        topic_file = tmp_path / "test.json"
        topic_file.write_text(json.dumps(topic_data))

        topic = _load_topic(tmp_path, "test")
        assert topic is not None
        assert topic.id == "test-topic"
        assert topic.slug == "test"
        assert topic.name == "Test Topic"
        assert topic.learning_steps == ()
        assert topic.questions == ()

    def test_full_topic_with_all_fields(self, tmp_path):
        """Loads topic with all optional fields."""
        topic_data = {
            "id": "full-topic",
            "slug": "full",
            "name": "Full Topic",
            "description": "A complete topic",
            "order": 2,
            "estimated_time": "45 mins",
            "is_capstone": True,
            "learning_steps": [
                {
                    "order": 1,
                    "text": "Step 1",
                    "action": "read",
                    "title": "Read docs",
                    "url": "https://docs.example.com",
                    "secondary_links": [{"text": "More", "url": "https://more.com"}],
                    "options": [
                        {
                            "provider": "azure",
                            "title": "Azure Guide",
                            "url": "https://azure.com",
                        }
                    ],
                }
            ],
            "questions": [
                {
                    "id": "q1",
                    "prompt": "What is X?",
                    "expected_concepts": ["concept1", "concept2"],
                }
            ],
            "learning_objectives": [
                {"id": "obj1", "text": "Learn X", "order": 1},
            ],
        }
        topic_file = tmp_path / "full.json"
        topic_file.write_text(json.dumps(topic_data))

        topic = _load_topic(tmp_path, "full")
        assert topic is not None
        assert topic.is_capstone is True
        assert topic.estimated_time == "45 mins"
        assert len(topic.learning_steps) == 1
        assert len(topic.questions) == 1
        assert len(topic.learning_objectives) == 1
        assert topic.learning_steps[0].secondary_links[0].text == "More"
        assert topic.learning_steps[0].options[0].provider == "azure"


class TestLoadPhaseWithMockedFiles:
    """Test _load_phase with mocked file system."""

    def test_phase_not_found(self, tmp_path):
        """Returns None when phase directory doesn't exist."""
        with patch("services.content_service.CONTENT_DIR", tmp_path):
            phase = _load_phase("nonexistent")
            assert phase is None

    def test_invalid_index_json(self, tmp_path):
        """Returns None on invalid index.json."""
        phase_dir = tmp_path / "bad_phase"
        phase_dir.mkdir()
        (phase_dir / "index.json").write_text("not json")

        with patch("services.content_service.CONTENT_DIR", tmp_path):
            phase = _load_phase("bad_phase")
            assert phase is None

    def test_valid_phase(self, tmp_path):
        """Loads phase with valid index.json."""
        phase_dir = tmp_path / "test_phase"
        phase_dir.mkdir()

        index_data = {
            "id": 99,
            "name": "Test Phase",
            "slug": "test_phase",
            "description": "A test phase",
            "short_description": "Test",
            "estimated_weeks": "1-2",
            "order": 99,
            "objectives": ["Learn testing"],
            "topics": [],
        }
        (phase_dir / "index.json").write_text(json.dumps(index_data))

        with patch("services.content_service.CONTENT_DIR", tmp_path):
            phase = _load_phase("test_phase")
            assert phase is not None
            assert phase.id == 99
            assert phase.name == "Test Phase"
            assert phase.capstone is None
            assert phase.hands_on_verification is None

    def test_phase_with_capstone(self, tmp_path):
        """Loads phase with capstone configuration."""
        phase_dir = tmp_path / "capstone_phase"
        phase_dir.mkdir()

        index_data = {
            "id": 1,
            "name": "Capstone Phase",
            "slug": "capstone_phase",
            "topics": [],
            "capstone": {
                "title": "Final Project",
                "summary": "Build something",
                "includes": ["Design", "Code"],
                "topic_slug": "final-project",
            },
        }
        (phase_dir / "index.json").write_text(json.dumps(index_data))

        with patch("services.content_service.CONTENT_DIR", tmp_path):
            phase = _load_phase("capstone_phase")
            assert phase is not None
            assert phase.capstone is not None
            assert phase.capstone.title == "Final Project"
            assert phase.capstone.topic_slug == "final-project"

    def test_phase_with_hands_on_verification(self, tmp_path):
        """Loads phase with hands-on verification config."""
        phase_dir = tmp_path / "hov_phase"
        phase_dir.mkdir()

        index_data = {
            "id": 2,
            "name": "HOV Phase",
            "slug": "hov_phase",
            "topics": [],
            "hands_on_verification": {
                "summary": "Prove your skills",
                "includes": ["GitHub", "Demo"],
            },
        }
        (phase_dir / "index.json").write_text(json.dumps(index_data))

        with patch("services.content_service.CONTENT_DIR", tmp_path):
            phase = _load_phase("hov_phase")
            assert phase is not None
            assert phase.hands_on_verification is not None
            assert "Prove" in phase.hands_on_verification.summary

    def test_phase_loads_topics(self, tmp_path):
        """Phase loads its topics from separate files."""
        phase_dir = tmp_path / "with_topics"
        phase_dir.mkdir()

        index_data = {
            "id": 3,
            "name": "With Topics",
            "slug": "with_topics",
            "topics": ["intro", "advanced"],
        }
        (phase_dir / "index.json").write_text(json.dumps(index_data))

        # Create topic files
        (phase_dir / "intro.json").write_text(
            json.dumps({"id": "t1", "slug": "intro", "name": "Intro"})
        )
        (phase_dir / "advanced.json").write_text(
            json.dumps({"id": "t2", "slug": "advanced", "name": "Advanced"})
        )

        with patch("services.content_service.CONTENT_DIR", tmp_path):
            phase = _load_phase("with_topics")
            assert phase is not None
            assert len(phase.topics) == 2
            assert phase.topics[0].slug == "intro"


class TestContentIntegration:
    """Integration tests with real content files."""

    def test_real_content_structure(self):
        """Verify real content has expected structure."""
        phases = get_all_phases()

        for phase in phases:
            # Phase has required fields
            assert phase.id is not None
            assert phase.name
            assert phase.slug

            # Topics have required fields
            for topic in phase.topics:
                assert topic.id
                assert topic.name
                assert topic.slug

    def test_all_questions_have_ids(self):
        """All questions across all topics have unique IDs."""
        question_ids = []
        for phase in get_all_phases():
            for topic in phase.topics:
                for q in topic.questions:
                    question_ids.append(q.id)

        # Check for duplicates
        assert len(question_ids) == len(set(question_ids)), "Duplicate question IDs"
