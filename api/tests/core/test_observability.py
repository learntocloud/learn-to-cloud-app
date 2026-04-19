"""Tests for core.observability — telemetry configuration."""

from __future__ import annotations

from unittest.mock import patch

import pytest


@pytest.mark.unit
class TestConfigureObservability:
    """Verify configure_observability behaviour."""

    def test_noop_without_connection_string(self) -> None:
        """When no APPLICATIONINSIGHTS_CONNECTION_STRING is set, telemetry stays off."""
        with patch.dict("os.environ", {}, clear=True):
            from importlib import reload

            import core.observability as obs_mod

            reload(obs_mod)
            obs_mod.configure_observability()
            assert not obs_mod._telemetry_enabled
