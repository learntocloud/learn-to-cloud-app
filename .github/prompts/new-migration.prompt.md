---
name: new-migration
description: Generate an Alembic migration for a database schema change.
---

Create an Alembic migration for the requested schema change.

## Before you start

1. Check `api/models.py` for the current model definitions.
2. Check `api/alembic/versions/` for recent migrations to understand naming and patterns.

## Steps

### 1. Update the model (`api/models.py`)
- Use `Mapped[T]` and `mapped_column()` for all columns.
- Use `TimestampMixin` if the table needs `created_at`/`updated_at`.
- For enums, use `class MyEnum(str, PyEnum)` with `native_enum=False` in the column.
- Add relationships with `back_populates` and appropriate cascade rules.
- Add constraints in `__table_args__`.

### 2. Generate the migration
```bash
cd api && uv run alembic revision --autogenerate -m "description_of_change"
```

### 3. Review the generated migration
- Open the new file in `api/alembic/versions/`.
- Verify the `upgrade()` and `downgrade()` functions are correct.
- Ensure indexes and constraints have explicit names.
- Check that `downgrade()` properly reverses all changes.

### 4. Test the migration
```bash
cd api && uv run alembic upgrade head
cd api && uv run alembic downgrade -1
cd api && uv run alembic upgrade head
```

### 5. Update dependent code
- If columns were added/renamed, update the relevant repository, service, and route layers.
- Update `schemas.py` if the API contract changed.
- Add or update tests.

## Validation
After generating, run: `cd api && uv run ruff check . && uv run ruff format --check . && uv run ty check`
