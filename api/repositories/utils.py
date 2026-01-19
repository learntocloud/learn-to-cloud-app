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
        db: The async database session
        model: The SQLAlchemy model class
        values: Dict of column name -> value for the insert
        index_elements: Column names that form the unique constraint
        update_fields: Column names to update on conflict
        returning: If True, return the upserted row (saves a round-trip)

    Returns:
        The upserted model instance if returning=True, else None

    Note:
        This function does NOT commit. The caller (typically the get_db
        dependency) is responsible for committing the transaction.
    """
    update_set = {field: values[field] for field in update_fields if field in values}

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
