"""Profile transaction error privacy without changing unrelated failures."""

import asyncio
import traceback
from unittest.mock import MagicMock

import pytest
from sqlalchemy.dialects.postgresql import asyncpg
from sqlalchemy.engine import ExceptionContext
from sqlalchemy.exc import (
    DataError,
    IntegrityError,
    OperationalError,
    SQLAlchemyError,
    StatementError,
    TimeoutError,
)

from learn_to_cloud_shared.core.profile_privacy import (
    ProfilePersistenceError,
    profile_persistence,
    sanitize_profile_database_error,
)


@pytest.mark.parametrize("error_class", [IntegrityError, DataError, OperationalError])
def test_statement_errors_remove_parameters_driver_details_and_chains(error_class):
    original = error_class(
        "UPDATE users SET display_name = :name",
        {"name": "Profile-Sentinel"},
        ValueError("Driver DETAIL Profile-Sentinel"),
    )
    original.__cause__ = ValueError("Driver cause Profile-Sentinel")
    with pytest.raises(ProfilePersistenceError) as caught, profile_persistence():
        raise original
    assert caught.value.error_type == error_class.__name__
    assert "Profile-Sentinel" not in "".join(traceback.format_exception(caught.value))
    assert caught.value.__cause__ is None
    assert caught.value.__suppress_context__


@pytest.mark.parametrize(
    ("original", "category"),
    [
        (TimeoutError("Profile-Sentinel"), "TimeoutError"),
        (SQLAlchemyError("Profile-Sentinel"), "SQLAlchemyError"),
        (
            StatementError(
                "Profile-Sentinel", "query", {"name": "Profile-Sentinel"}, ValueError()
            ),
            "StatementError",
        ),
        (type("Profile-Sentinel", (SQLAlchemyError,), {})(), "SQLAlchemyError"),
    ],
)
def test_error_categories_are_bounded(original, category):
    with pytest.raises(ProfilePersistenceError) as caught, profile_persistence():
        raise original
    assert str(caught.value) == f"Profile persistence failed ({category})"


def test_error_context_is_sanitized_only_inside_profile_scope():
    original = ValueError("Driver DETAIL Profile-Sentinel")
    wrapped = OperationalError("query", {"name": "Profile-Sentinel"}, original)
    context = MagicMock(spec=ExceptionContext)
    context.original_exception = original
    context.sqlalchemy_exception = wrapped
    context.is_disconnect = True
    context.invalidate_pool_on_disconnect = True

    assert sanitize_profile_database_error(context) is None
    assert context.original_exception is original
    with profile_persistence():
        replacement = sanitize_profile_database_error(context)
    assert context.original_exception is original
    assert str(replacement) == "Profile persistence failed (OperationalError)"
    assert replacement.__cause__ is None
    assert replacement.__context__ is None
    assert context.is_disconnect is True
    assert context.invalidate_pool_on_disconnect is True
    assert context.sqlalchemy_exception is wrapped
    assert str(original) == str(replacement)
    assert sanitize_profile_database_error(context) is None


def test_non_database_failure_propagates_and_resets_scope():
    error = RuntimeError("unrelated failure")
    with pytest.raises(RuntimeError) as caught, profile_persistence():
        raise error
    assert caught.value is error
    assert sanitize_profile_database_error(MagicMock(spec=ExceptionContext)) is None


@pytest.mark.parametrize(
    "error_type",
    [
        "Error",
        "InterfaceError",
        "DatabaseError",
        "InternalError",
        "OperationalError",
        "ProgrammingError",
        "IntegrityError",
        "DataError",
        "NotSupportedError",
        "InternalServerError",
        "InternalClientError",
        "InvalidCachedStatementError",
    ],
)
def test_asyncpg_dbapi_error_contract(error_type):
    dbapi = asyncpg.dialect.import_dbapi()
    original = getattr(dbapi, error_type)("Driver DETAIL Profile-Sentinel")
    original.sqlstate = "23514"
    original.__cause__ = ValueError("Driver cause Profile-Sentinel")
    original.__context__ = ValueError("Driver context Profile-Sentinel")
    context = MagicMock(spec=ExceptionContext)
    context.original_exception = original
    context.sqlalchemy_exception = IntegrityError(
        "query", {"name": "Profile-Sentinel"}, original
    )
    with profile_persistence():
        replacement = sanitize_profile_database_error(context)
    assert str(original) == str(replacement)
    assert "Profile-Sentinel" not in "".join(traceback.format_exception(original))
    assert type(original) is getattr(dbapi, error_type)
    assert original.sqlstate == "23514"


def test_unwrapped_error_is_not_replaced():
    context = MagicMock(spec=ExceptionContext)
    context.original_exception = RuntimeError("unrelated failure")
    context.sqlalchemy_exception = None
    with profile_persistence():
        assert sanitize_profile_database_error(context) is None
    assert str(context.original_exception) == "unrelated failure"


async def test_profile_scope_does_not_affect_concurrent_transactions():
    entered = asyncio.Event()
    checked = asyncio.Event()

    async def profile():
        with profile_persistence():
            entered.set()
            await checked.wait()
            context = MagicMock(spec=ExceptionContext)
            context.sqlalchemy_exception = SQLAlchemyError()
            context.original_exception = ValueError()
            assert isinstance(
                sanitize_profile_database_error(context), ProfilePersistenceError
            )

    async def unrelated():
        await entered.wait()
        try:
            assert (
                sanitize_profile_database_error(MagicMock(spec=ExceptionContext))
                is None
            )
        finally:
            checked.set()

    await asyncio.gather(profile(), unrelated())
