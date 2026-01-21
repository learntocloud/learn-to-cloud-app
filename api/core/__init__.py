"""Core utilities for the Learn to Cloud API.

This module exports commonly used utilities for easy importing:
    from core import get_logger
"""

from core.logger import bind_contextvars, clear_contextvars, get_logger
from core.wide_event import (
    get_wide_event,
    set_wide_event_field,
    set_wide_event_fields,
    set_wide_event_nested,
)

__all__ = [
    "get_logger",
    "bind_contextvars",
    "clear_contextvars",
    "get_wide_event",
    "set_wide_event_field",
    "set_wide_event_fields",
    "set_wide_event_nested",
]
