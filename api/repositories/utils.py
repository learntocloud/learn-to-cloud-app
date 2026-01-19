"""Repository utility functions for common database operations."""

from typing import Any

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession


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
