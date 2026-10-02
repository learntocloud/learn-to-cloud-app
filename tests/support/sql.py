"""Capture SQL emitted through a SQLAlchemy engine or connection."""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from sqlalchemy import event


@contextmanager
def captured_statements(target: Any) -> Iterator[list[str]]:
    """Yield the lowercased SQL statements executed on ``target`` while open."""
    statements: list[str] = []

    def record(**event_args: Any) -> None:
        statements.append(event_args["statement"].lower())

    event.listen(target, "before_cursor_execute", record, named=True)
    try:
        yield statements
    finally:
        event.remove(target, "before_cursor_execute", record)
