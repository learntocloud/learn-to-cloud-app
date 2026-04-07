"""Tests for core.observability — agent-framework provider isolation."""

from __future__ import annotations

from unittest.mock import patch

import pytest


@pytest.mark.unit
class TestAgentFrameworkInstrumentation:
    """Verify _enable_agent_framework_instrumentation uses the public API."""

    def test_activates_instrumentation(self) -> None:
        from agent_framework.observability import OBSERVABILITY_SETTINGS

        original = OBSERVABILITY_SETTINGS.enable_instrumentation
        try:
            OBSERVABILITY_SETTINGS.enable_instrumentation = False

            from core.observability import _enable_agent_framework_instrumentation

            _enable_agent_framework_instrumentation()

            assert OBSERVABILITY_SETTINGS.ENABLED is True
        finally:
            OBSERVABILITY_SETTINGS.enable_instrumentation = original

    def test_does_not_create_providers(self) -> None:
        """enable_instrumentation() must not call _configure_providers."""
        from agent_framework.observability import OBSERVABILITY_SETTINGS

        original = OBSERVABILITY_SETTINGS.enable_instrumentation
        try:
            OBSERVABILITY_SETTINGS.enable_instrumentation = False

            with patch.object(
                OBSERVABILITY_SETTINGS, "_configure_providers"
            ) as mock_configure:
                from core.observability import _enable_agent_framework_instrumentation

                _enable_agent_framework_instrumentation()
                mock_configure.assert_not_called()
        finally:
            OBSERVABILITY_SETTINGS.enable_instrumentation = original

    def test_graceful_when_framework_missing(self) -> None:
        """Module import fails when agent-framework is not installed.

        agent_framework is a required dependency, so this verifies
        the expected ImportError rather than silent degradation.
        """
        with patch.dict(
            "sys.modules",
            {
                "agent_framework": None,
                "agent_framework.observability": None,
            },
        ):
            from importlib import reload

            import core.observability as obs_mod

            with pytest.raises(ImportError):
                reload(obs_mod)
