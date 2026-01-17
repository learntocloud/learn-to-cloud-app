"""Repository utility functions for common database operations."""

from typing import Any, TypeVar

from sqlalchemy.ext.asyncio import AsyncSession

T = TypeVar("T")


async def upsert_on_conflict(
    db: AsyncSession,
    model: type[T],
    values: dict[str, Any],
    index_elements: list[str],
    update_fields: list[str],
    *,
    returning: bool = False,
) -> T | None:
    """
    Perform a dialect-aware upsert (INSERT ... ON CONFLICT DO UPDATE).

    Supports PostgreSQL and SQLite. Falls back to select-then-update for
    other dialects.

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
        dependency) is responsible for committing the transaction. This
        allows multiple upserts to be composed atomically.
    """
    bind = db.get_bind()
    dialect_name = bind.dialect.name if bind is not None else ""

    update_set = {field: values[field] for field in update_fields if field in values}

    if dialect_name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert as pg_insert

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

    elif dialect_name == "sqlite":
        from sqlalchemy.dialects.sqlite import insert as sqlite_insert

        stmt = sqlite_insert(model).values(**values)
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

    else:
        # Fallback: select-then-update (not atomic, for unsupported dialects)
        from sqlalchemy import and_, select

        conditions = [getattr(model, elem) == values[elem] for elem in index_elements]
        result = await db.execute(select(model).where(and_(*conditions)))
        existing = result.scalar_one_or_none()

        if existing:
            for field in update_fields:
                if field in values:
                    setattr(existing, field, values[field])
            await db.flush()
            return existing if returning else None
        else:
            instance = model(**values)
            db.add(instance)
            await db.flush()
            return instance if returning else None
