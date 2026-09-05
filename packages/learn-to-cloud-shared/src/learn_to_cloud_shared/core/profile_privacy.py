"""Value-free errors for the OAuth profile persistence transaction."""

from collections.abc import Generator
from contextlib import contextmanager
from contextvars import ContextVar

from sqlalchemy.engine import ExceptionContext
from sqlalchemy.exc import (
    DataError,
    IntegrityError,
    OperationalError,
    SQLAlchemyError,
    StatementError,
    TimeoutError,
)

_profile_persistence_active = ContextVar("profile_persistence_active", default=False)


class ProfilePersistenceError(SQLAlchemyError):
    """A database failure without profile values or driver diagnostics."""

    def __init__(self, error: SQLAlchemyError | None) -> None:
        if isinstance(error, ProfilePersistenceError):
            self.error_type = error.error_type
        else:
            self.error_type = next(
                (
                    error_class.__name__
                    for error_class in (
                        IntegrityError,
                        DataError,
                        OperationalError,
                        TimeoutError,
                        StatementError,
                    )
                    if isinstance(error, error_class)
                ),
                "SQLAlchemyError",
            )
        super().__init__(f"Profile persistence failed ({self.error_type})")


def sanitize_profile_database_error(
    context: ExceptionContext,
) -> ProfilePersistenceError | None:
    """Sanitize the public error context before dependency telemetry observes it."""
    if not _profile_persistence_active.get() or context.sqlalchemy_exception is None:
        return None

    error = ProfilePersistenceError(context.sqlalchemy_exception)
    # OTel's handle_error listener reads original_exception, not the replacement
    # returned by earlier listeners. The asyncpg dialect's DBAPI errors use
    # standard Exception.args; preserve their types and SQLSTATE for cleanup.
    original = context.original_exception
    original.args = error.args
    original.__cause__ = None
    original.__context__ = None
    original.__suppress_context__ = True
    return error


@contextmanager
def profile_persistence() -> Generator[None]:
    """Protect profile writes, commit, and session cleanup without swallowing errors."""
    token = _profile_persistence_active.set(True)
    try:
        yield
    except SQLAlchemyError as exc:
        # SQLAlchemy explicitly chains even handle_error replacements to the
        # driver error. Do not let that chain reach request telemetry or logging.
        raise ProfilePersistenceError(exc) from None
    finally:
        _profile_persistence_active.reset(token)
