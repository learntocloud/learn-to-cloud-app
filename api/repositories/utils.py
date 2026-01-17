"""Repository utility functions for common database operations."""

from sqlalchemy.ext.asyncio import AsyncSession


async def upsert_on_conflict(
    db: AsyncSession,
    model: type,
    values: dict,
    index_elements: list[str],
    update_fields: list[str],
) -> None:
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
        await db.execute(stmt)

    elif dialect_name == "sqlite":
        from sqlalchemy.dialects.sqlite import insert as sqlite_insert

        stmt = sqlite_insert(model).values(**values)
        stmt = stmt.on_conflict_do_update(
            index_elements=index_elements,
            set_=update_set,
        )
        await db.execute(stmt)

    else:
        from sqlalchemy import and_, select

        conditions = [getattr(model, elem) == values[elem] for elem in index_elements]
        result = await db.execute(select(model).where(and_(*conditions)))
        existing = result.scalar_one_or_none()

        if existing:
            for field in update_fields:
                if field in values:
                    setattr(existing, field, values[field])
        else:
            db.add(model(**values))
        await db.flush()
