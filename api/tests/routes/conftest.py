"""Route test configuration — disable rate limiter for unit tests."""

from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def _disable_rate_limiter():
    """Disable slowapi rate limiting so route handlers can be called directly."""
    with patch("core.ratelimit.limiter.enabled", False):
        yield
