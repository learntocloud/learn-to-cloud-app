"""Tests for content service."""

import tempfile
from pathlib import Path

import pytest

from services.content_service import (
    _load_phase,
    _load_topic,
    clear_cache,
    get_all_phases,
    get_phase_by_slug,
    get_topic_by_id,
    get_topic_by_slugs,
)

# Mark all tests in this module as unit tests (no database required)
pytestmark = pytest.mark.unit


class TestContentService:
    """Tests for content loading service."""

    @pytest.fixture(autouse=True)
    def clear_content_cache(self):
        """Clear content cache before and after each test."""
        clear_cache()
        yield
        clear_cache()

    def test_get_all_phases_returns_tuple(self):
        """Test that get_all_phases returns a tuple of phases."""
        phases = get_all_phases()
        assert isinstance(phases, tuple)

    def test_get_all_phases_returns_phases_in_order(self):
        """Test that phases are returned in order by their order attribute."""
        phases = get_all_phases()
        if len(phases) > 1:
            orders = [p.order for p in phases]
            assert orders == sorted(orders)

    def test_get_all_phases_caches_result(self):
        """Test that get_all_phases caches results."""
        phases1 = get_all_phases()
        phases2 = get_all_phases()
        assert phases1 is phases2

    def test_get_phase_by_slug_found(self):
        """Test getting a phase by slug that exists."""
        phases = get_all_phases()
        if phases:
            first_phase = phases[0]
            result = get_phase_by_slug(first_phase.slug)
            assert result is not None
            assert result.slug == first_phase.slug

    def test_get_phase_by_slug_not_found(self):
        """Test getting a phase by non-existent slug."""
        result = get_phase_by_slug("nonexistent-phase-slug")
        assert result is None

    def test_get_topic_by_id_found(self):
        """Test getting a topic by ID that exists."""
        phases = get_all_phases()
        if phases and phases[0].topics:
            first_topic = phases[0].topics[0]
            result = get_topic_by_id(first_topic.id)
            assert result is not None
            assert result.id == first_topic.id

    def test_get_topic_by_id_not_found(self):
        """Test getting a topic by non-existent ID."""
        result = get_topic_by_id("nonexistent-topic-id")
        assert result is None

    def test_get_topic_by_slugs_found(self):
        """Test getting a topic by phase and topic slugs."""
        phases = get_all_phases()
        if phases and phases[0].topics:
            phase = phases[0]
            topic = phase.topics[0]
            result = get_topic_by_slugs(phase.slug, topic.slug)
            assert result is not None
            assert result.slug == topic.slug

    def test_get_topic_by_slugs_phase_not_found(self):
        """Test getting a topic with non-existent phase slug."""
        result = get_topic_by_slugs("nonexistent-phase", "some-topic")
        assert result is None

    def test_get_topic_by_slugs_topic_not_found(self):
        """Test getting a topic with non-existent topic slug."""
        phases = get_all_phases()
        if phases:
            result = get_topic_by_slugs(phases[0].slug, "nonexistent-topic")
            assert result is None

    def test_clear_cache_clears_phases(self):
        """Test that clear_cache clears the phase cache."""
        # Load phases to populate cache
        phases1 = get_all_phases()

        # Clear cache
        clear_cache()

        # Load again - should be same content but potentially different object
        phases2 = get_all_phases()

        # Content should be equivalent
        assert len(phases1) == len(phases2)


class TestLoadPhase:
    """Tests for _load_phase function."""

    @pytest.fixture(autouse=True)
    def clear_content_cache(self):
        """Clear content cache before and after each test."""
        clear_cache()
        yield
        clear_cache()

    def test_load_phase_nonexistent_returns_none(self):
        """Test that _load_phase returns None for non-existent phase."""
        result = _load_phase("nonexistent-phase-xyz")
        assert result is None


class TestLoadTopic:
    """Tests for _load_topic function."""

    def test_load_topic_nonexistent_file_returns_none(self):
        """Test that _load_topic returns None when topic file doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            phase_dir = Path(tmpdir) / "phase0"
            phase_dir.mkdir()
            result = _load_topic(phase_dir, "nonexistent-topic")
            assert result is None

    def test_load_topic_invalid_json_returns_none(self):
        """Test that _load_topic returns None for invalid JSON."""
        with tempfile.TemporaryDirectory() as tmpdir:
            phase_dir = Path(tmpdir) / "phase0"
            phase_dir.mkdir()

            # Create invalid JSON file
            topic_file = phase_dir / "bad-topic.json"
            topic_file.write_text("{ invalid json }")

            result = _load_topic(phase_dir, "bad-topic")
            assert result is None

    def test_load_topic_missing_required_fields_returns_none(self):
        """Test that _load_topic returns None when required fields are missing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            phase_dir = Path(tmpdir) / "phase0"
            phase_dir.mkdir()

            # Create JSON missing required fields
            topic_file = phase_dir / "incomplete-topic.json"
            topic_file.write_text('{"description": "missing id, slug, name"}')

            result = _load_topic(phase_dir, "incomplete-topic")
            assert result is None


class TestPhaseStructure:
    """Tests for phase and topic data structure."""

    def test_phases_have_required_fields(self):
        """Test that all phases have required fields."""
        phases = get_all_phases()
        for phase in phases:
            assert phase.id is not None
            assert phase.name
            assert phase.slug
            assert isinstance(phase.topics, list)

    def test_topics_have_required_fields(self):
        """Test that all topics have required fields."""
        phases = get_all_phases()
        for phase in phases:
            for topic in phase.topics:
                assert topic.id
                assert topic.slug
                assert topic.name
                assert isinstance(topic.learning_steps, list)
                assert isinstance(topic.questions, list)

    def test_learning_steps_have_required_fields(self):
        """Test that all learning steps have required fields."""
        phases = get_all_phases()
        for phase in phases:
            for topic in phase.topics:
                for step in topic.learning_steps:
                    assert step.order >= 1
                    assert step.text is not None

    def test_questions_have_required_fields(self):
        """Test that all questions have required fields."""
        phases = get_all_phases()
        for phase in phases:
            for topic in phase.topics:
                for question in topic.questions:
                    assert question.id
                    assert question.prompt
