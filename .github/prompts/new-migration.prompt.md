---
name: new-migration
description: Generate an Alembic migration for a database schema change.
---

Create an Alembic migration for the requested schema change.

## Before you start

1. Check `src/learn_to_cloud/models.py` for the current model definitions.
2. Check `alembic/versions/` for recent migrations to understand naming and patterns.

## Steps

### 1. Update the shared model (`src/learn_to_cloud/models.py`)
- Use `Mapped[T]` and `mapped_column()` for all columns.
- Use `TimestampMixin` if the table needs `created_at`/`updated_at`.
- For enums, use `class MyEnum(str, PyEnum)` with `native_enum=False` in the column.
- Add relationships with `back_populates` and appropriate cascade rules.
- Add constraints in `__table_args__`.

### 2. Generate the migration
```bash
uv run alembic revision --autogenerate -m "description_of_change"
```

### 3. Review the generated migration
- Open the new file in `alembic/versions/`.
- Verify the `upgrade()` and `downgrade()` functions are correct.
- Ensure indexes and constraints have explicit names.
- Check that `downgrade()` properly reverses all changes.

### 4. Test the migration
```bash
uv run alembic upgrade head
uv run alembic downgrade -1
uv run alembic upgrade head
```

### 5. Update dependent code
- If columns were added/renamed, update the relevant repository, service, and route layers.
- Update the matching `schemas/` module if the API contract changed.
- Add or update tests.

## Validation
After generating, run: `uv run ruff check . && uv run ruff format --check . && uv run ty check`
