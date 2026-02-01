"""Wide Event context for canonical log lines.

Provides a request-scoped dict for accumulating context throughout the request
lifecycle. Middleware handles initialization at request start and emission at
request end.

This module only manages the data structure - telemetry.py handles lifecycle.

Usage:
    from core.wide_event import set_wide_event_fields

    # In route handlers or services:
    set_wide_event_fields(cart_id=cart.id, cart_total_cents=cart.total)

    # For nested data:
    set_wide_event_nested("payment", method="card", provider="stripe")
"""

from contextvars import ContextVar
from typing import Any

_wide_event: ContextVar[dict[str, Any]] = ContextVar("wide_event")


def init_wide_event() -> dict[str, Any]:
    """Initialize a new wide event dict for the current async context.

    Called by RequestTimingMiddleware at request start.
    """
    event: dict[str, Any] = {}
    _wide_event.set(event)
    return event


def get_wide_event() -> dict[str, Any]:
    """Get the current wide event dict. Returns empty dict if not initialized."""
    try:
        return _wide_event.get()
    except LookupError:
        return {}


def set_wide_event_field(key: str, value: Any) -> None:
    """Set a single field on the current wide event.

    No-op if called outside request context (e.g., CLI, background tasks, tests).
    Telemetry should never crash the app.
    """
    event = get_wide_event()
    if event:
        event[key] = value


def set_wide_event_fields(**kwargs: Any) -> None:
    """Set multiple fields on the current wide event.

    No-op if called outside request context (e.g., CLI, background tasks, tests).
    Telemetry should never crash the app.
    """
    event = get_wide_event()
    if event:
        event.update(kwargs)


def set_wide_event_nested(category: str, **kwargs: Any) -> None:
    """Set fields in a nested category (e.g., user, payment, cart).

    No-op if called outside request context (e.g., CLI, background tasks, tests).
    Telemetry should never crash the app.

    Example:
        set_wide_event_nested("user", id="123", subscription="premium")
        # Results in: {"user": {"id": "123", "subscription": "premium"}}
    """
    event = get_wide_event()
    if not event:
        return
    if category not in event:
        event[category] = {}
    event[category].update(kwargs)


def clear_wide_event() -> None:
    """Clear the wide event for the current context.

    Called by RequestTimingMiddleware after emitting the event.
    """
    _wide_event.set({})
