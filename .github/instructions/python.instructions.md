---
applyTo: '**/*.py'
---

# Python Coding Standards

## Style
- Follow PEP 8
- Use type hints for all function signatures
- Use async/await for all database operations
- Maximum line length: 88 characters (ruff default)

## Imports
- Group imports: stdlib → third-party → local
- Use absolute imports within the api package
- Sort imports alphabetically within groups

## Naming
- Functions/variables: `snake_case`
- Classes: `PascalCase`
- Constants: `UPPER_SNAKE_CASE`

## Dependencies
- Managed with `uv` (not pip)
- Add to `pyproject.toml`, not requirements.txt
- Run `uv sync` to install

## Testing
- Test files: `test_*.py`
- Use pytest fixtures from `conftest.py`
- Mock external services (Clerk, LLM, GitHub API)
