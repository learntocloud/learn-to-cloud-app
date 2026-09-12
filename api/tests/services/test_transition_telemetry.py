"""Tests for privacy-preserving phase transition identifiers."""

from unittest.mock import MagicMock, patch

import pytest

from learn_to_cloud.services.transition_telemetry import (
    build_phase_transition_id,
    is_valid_phase_transition_id,
)

pytestmark = pytest.mark.unit


def test_transition_id_is_stable_and_scoped() -> None:
    settings = MagicMock()
    settings.session.secret_key = "test-secret"

    with patch(
        "learn_to_cloud.services.transition_telemetry.get_web_settings",
        return_value=settings,
    ):
        transition_id = build_phase_transition_id(12345, source_phase=1, target_phase=2)
        repeated = build_phase_transition_id(12345, source_phase=1, target_phase=2)
        different_phase = build_phase_transition_id(
            12345, source_phase=2, target_phase=3
        )

    assert transition_id == repeated
    assert transition_id != different_phase
    assert "12345" not in transition_id
    assert len(transition_id) == 24

    with patch(
        "learn_to_cloud.services.transition_telemetry.get_web_settings",
        return_value=settings,
    ):
        assert is_valid_phase_transition_id(
            transition_id,
            12345,
            source_phase=1,
            target_phase=2,
        )
        assert not is_valid_phase_transition_id(
            transition_id,
            54321,
            source_phase=1,
            target_phase=2,
        )
