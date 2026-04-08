---
applyTo: "**/*.py"
---

# Python Conventions

These supplement the project-wide rules in `copilot-instructions.md`.

## Typing
- Use `str | None` union syntax, not `Optional[str]`.
- Enums: `class MyEnum(StrEnum)` (`enum.StrEnum`) with `native_enum=False` in column definitions.

## Async
- Async test fixtures use `@pytest_asyncio.fixture`.

## Architecture Layers
- **Services**: No HTTP knowledge, no `Request` objects. Accept `AsyncSession` as parameter.

## Logging
- Module-level logger: `logger = logging.getLogger(__name__)`
- Structured logging with `extra={}` dicts — never f-strings for log messages.
- Event names use dot-notation: `"user.account_deleted"`, `"step.completed"`.
- Always include relevant IDs in extra: `user_id`, `step_id`, `phase_id`.
- Use `logger.exception()` in except blocks (auto-includes traceback).

## Service Layer
- Verification services return `ValidationResult(is_valid, message, task_results=[...])`.
- Custom exceptions carry a `retriable: bool` flag.
- External API calls use circuit breaker + retry decorators (`circuitbreaker` + `tenacity`).

## Testing
- Use `factory-boy` and `faker` for test data.
- `asyncio_mode = auto` — no manual `@pytest.mark.asyncio` needed.
- Always tag tests: `@pytest.mark.unit` or `@pytest.mark.integration`.
- `db_session` fixture auto-rolls back transactions.
- Mock with `autospec=True` always. Use `AsyncMock()` for async methods.

## Formatting
- Import sorting: isort-compatible via ruff.
