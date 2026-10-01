"""Helpers for tenacity-decorated functions in tests."""

from collections.abc import Awaitable, Callable
from typing import Any


def retry_with[R](
    function: Callable[..., Awaitable[R]], **overrides: Any
) -> Callable[..., Awaitable[R]]:
    """Return a copy of a tenacity-decorated function with retry overrides."""
    # tenacity attaches retry_with at runtime; its type hints don't declare it.
    return getattr(function, "retry_with")(**overrides)
