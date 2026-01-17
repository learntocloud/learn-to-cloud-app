"""Unit tests for ID parsing functions in services/progress.py.

Tests the internal parser functions that extract phase numbers from topic
and question IDs.

Total test cases: 18
- TestParsePhaseFromTopicId: 9 tests
- TestParsePhaseFromQuestionId: 9 tests
"""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from services.progress import _parse_phase_from_question_id, _parse_phase_from_topic_id


class TestParsePhaseFromTopicId:
    """Test _parse_phase_from_topic_id function.

    Expected format: phase{N}-topic{M}
    Examples: phase0-topic1, phase1-topic3, phase6-topic5
    """

    @pytest.mark.parametrize(
        "topic_id,expected_phase",
        [
            ("phase0-topic1", 0),
            ("phase1-topic3", 1),
            ("phase2-topic5", 2),
            ("phase3-topic2", 3),
            ("phase4-topic7", 4),
            ("phase5-topic4", 5),
            ("phase6-topic6", 6),
        ],
    )
    def test_valid_topic_ids(self, topic_id, expected_phase):
        """Parse valid topic IDs for all 7 phases."""
        result = _parse_phase_from_topic_id(topic_id)
        assert result == expected_phase

    def test_invalid_format_returns_none(self):
        """Invalid format returns None."""
        assert _parse_phase_from_topic_id("invalid-format") is None

    def test_non_string_returns_none(self):
        """Non-string input returns None."""
        assert _parse_phase_from_topic_id(123) is None
        assert _parse_phase_from_topic_id(None) is None

    def test_empty_string_returns_none(self):
        """Empty string returns None."""
        assert _parse_phase_from_topic_id("") is None

    def test_missing_dash_returns_none(self):
        """Topic ID without dash returns None."""
        assert _parse_phase_from_topic_id("phase0topic1") is None

    def test_non_numeric_phase_returns_none(self):
        """Non-numeric phase number returns None."""
        assert _parse_phase_from_topic_id("phasex-topic1") is None

    def test_negative_phase_number(self):
        """Negative phase number returns None (invalid format)."""
        result = _parse_phase_from_topic_id("phase-1-topic1")
        assert result is None

    def test_topic_id_with_extra_dashes(self):
        """Topic ID with extra dashes parses correctly."""
        result = _parse_phase_from_topic_id("phase2-topic3-extra")
        assert result == 2

    @given(phase_num=st.integers(min_value=0, max_value=1000))
    def test_large_phase_numbers(self, phase_num):
        """Parser handles arbitrarily large phase numbers."""
        topic_id = f"phase{phase_num}-topic1"
        result = _parse_phase_from_topic_id(topic_id)
        assert result == phase_num


class TestParsePhaseFromQuestionId:
    """Test _parse_phase_from_question_id function.

    Expected format: phase{N}-topic{M}-q{X}
    Examples: phase0-topic1-q1, phase1-topic2-q2, phase6-topic4-q1
    """

    @pytest.mark.parametrize(
        "question_id,expected_phase",
        [
            ("phase0-topic1-q1", 0),
            ("phase1-topic2-q2", 1),
            ("phase2-topic3-q1", 2),
            ("phase3-topic1-q2", 3),
            ("phase4-topic5-q1", 4),
            ("phase5-topic2-q2", 5),
            ("phase6-topic4-q1", 6),
        ],
    )
    def test_valid_question_ids(self, question_id, expected_phase):
        """Parse valid question IDs for all 7 phases."""
        result = _parse_phase_from_question_id(question_id)
        assert result == expected_phase

    def test_invalid_format_returns_none(self):
        """Invalid format returns None."""
        assert _parse_phase_from_question_id("invalid-format") is None

    def test_non_string_returns_none(self):
        """Non-string input returns None."""
        assert _parse_phase_from_question_id(123) is None
        assert _parse_phase_from_question_id(None) is None

    def test_empty_string_returns_none(self):
        """Empty string returns None."""
        assert _parse_phase_from_question_id("") is None

    def test_missing_dashes_returns_none(self):
        """Question ID without dashes returns None."""
        assert _parse_phase_from_question_id("phase0topic1q1") is None

    def test_non_numeric_phase_returns_none(self):
        """Non-numeric phase number returns None."""
        assert _parse_phase_from_question_id("phasex-topic1-q1") is None

    def test_topic_id_format_returns_phase(self):
        """Topic ID format (without q suffix) still parses phase."""
        result = _parse_phase_from_question_id("phase2-topic3")
        assert result == 2

    def test_question_id_with_extra_dashes(self):
        """Question ID with extra dashes parses correctly."""
        result = _parse_phase_from_question_id("phase3-topic2-q1-extra")
        assert result == 3

    @given(phase_num=st.integers(min_value=0, max_value=1000))
    def test_large_phase_numbers(self, phase_num):
        """Parser handles arbitrarily large phase numbers."""
        question_id = f"phase{phase_num}-topic1-q1"
        result = _parse_phase_from_question_id(question_id)
        assert result == phase_num
