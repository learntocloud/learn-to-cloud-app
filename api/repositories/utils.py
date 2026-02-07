"""Repository utility functions for common database operations."""

import time
from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Any, ParamSpec, TypeVar

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from core.logger import get_logger
from core.wide_event import set_wide_event_fields

logger = get_logger(__name__)

# Threshold for logging slow queries (milliseconds)
SLOW_QUERY_THRESHOLD_MS = 500

P = ParamSpec("P")
R = TypeVar("R")


def log_slow_query(
    operation_name: str,
) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[R]]]:
    """Decorator to log slow repository operations and errors.

    Logs at DEBUG level for queries exceeding SLOW_QUERY_THRESHOLD_MS.
    Logs at ERROR level for exceptions (re-raises after logging).

    Usage:
        @log_slow_query("get_user_by_id")
        async def get_by_id(self, user_id: int) -> User | None:
            ...
    """

    def decorator(func: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            start_time = time.perf_counter()
            try:
                result = await func(*args, **kwargs)
                duration_ms = (time.perf_counter() - start_time) * 1000
                if duration_ms > SLOW_QUERY_THRESHOLD_MS:
                    set_wide_event_fields(
                        db_slow_query=True,
                        db_operation=operation_name,
                        db_duration_ms=round(duration_ms, 2),
                    )
                return result
            except Exception as e:
                duration_ms = (time.perf_counter() - start_time) * 1000
                set_wide_event_fields(
                    db_query_error=True,
                    db_operation=operation_name,
                    db_duration_ms=round(duration_ms, 2),
                    db_error=str(e),
                    db_error_type=type(e).__name__,
                )
                raise

        return wrapper

    return decorator


async def upsert_on_conflict[T](
    db: AsyncSession,
    model: type[T],
    values: dict[str, Any],
    index_elements: list[str],
    update_fields: list[str],
    *,
    returning: bool = False,
) -> T | None:
    """
    Perform an upsert (INSERT ... ON CONFLICT DO UPDATE).

    Args:
        values: Column name -> value mapping for insert.
        index_elements: Columns forming the unique constraint to match on.
        update_fields: Columns to update when conflict occurs.
        returning: Return the upserted row (saves a SELECT round-trip).

    Note:
        Does NOT commit. Caller owns the transaction.

    Warning:
        Column.onupdate triggers are NOT applied during ON CONFLICT DO UPDATE.
        You MUST manually include 'updated_at' in both `values` and `update_fields`.
        See: https://docs.sqlalchemy.org/en/20/dialects/postgresql.html#the-set-clause
    """
    update_set = {field: values[field] for field in update_fields if field in values}

    if not update_set:
        raise ValueError(
            f"No valid update fields: update_fields={update_fields} "
            f"but values only contains keys {list(values.keys())}"
        )

    stmt = pg_insert(model).values(**values)
    stmt = stmt.on_conflict_do_update(
        index_elements=index_elements,
        set_=update_set,
    )
    if returning:
        stmt = stmt.returning(model)
        result = await db.execute(stmt)
        return result.scalar_one()
    await db.execute(stmt)
    return None
