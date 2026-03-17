---
applyTo: "**/*.py"
---

# Python Conventions

These supplement the project-wide rules in `copilot-instructions.md`.

## Typing
- Use `str | None` union syntax, not `Optional[str]`.
- Enums: `class MyEnum(str, PyEnum)` with `native_enum=False` in column definitions.

## Async
- Async test fixtures use `@pytest_asyncio.fixture`.

## Architecture Layers
- **Services**: No HTTP knowledge, no `Request` objects. Accept `AsyncSession` as parameter.

## Logging
- Module-level logger: `logger = logging.getLogger(__name__)`

## Testing
- Use `factory-boy` and `faker` for test data.

## Formatting
- Import sorting: isort-compatible via ruff.
