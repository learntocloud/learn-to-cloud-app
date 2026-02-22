"""Unit tests for legacy redirect routes.

Tests cover:
- GET /phase{N} — redirects to / with 301
- GET /phase{N}/{path} — redirects to / with 301

These are the simplest routes: no auth, no DB, pure redirect logic.
"""

import pytest

from routes.legacy_redirects import legacy_phase_redirect


@pytest.mark.unit
class TestLegacyPhaseRedirect:
    """Tests for /phase{N} and /phase{N}/{rest} redirects."""

    async def test_phase0_redirects_to_home(self):
        """GET /phase0 returns 301 redirect to /."""
        result = await legacy_phase_redirect(phase_num=0)
        assert result.status_code == 301
        assert result.headers["location"] == "/"

    async def test_phase5_with_subpath_redirects_to_home(self):
        """GET /phase5/some-topic returns 301 redirect to /."""
        result = await legacy_phase_redirect(phase_num=5, rest="some-topic")
        assert result.status_code == 301
        assert result.headers["location"] == "/"

    async def test_deep_nested_path_redirects_to_home(self):
        """GET /phase1/deeply/nested/path returns 301 redirect to /."""
        result = await legacy_phase_redirect(phase_num=1, rest="deeply/nested/path")
        assert result.status_code == 301
        assert result.headers["location"] == "/"

    async def test_redirect_is_permanent(self):
        """Legacy redirects use 301 (permanent), not 302 (temporary)."""
        result = await legacy_phase_redirect(phase_num=3)
        assert result.status_code == 301

    async def test_all_phase_numbers_redirect(self):
        """All documented phases (0-5) redirect correctly."""
        for phase_num in range(6):
            result = await legacy_phase_redirect(phase_num=phase_num, rest="")
            assert result.status_code == 301
            assert result.headers["location"] == "/"
