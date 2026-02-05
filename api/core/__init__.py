"""Core utilities for the Learn to Cloud API.

This module exports commonly used utilities for easy importing:
    from core import get_logger
"""

from core.logger import get_logger
from core.wide_event import (
    get_wide_event,
    set_wide_event_fields,
)

__all__ = [
    "get_logger",
    "get_wide_event",
    "set_wide_event_fields",
]
