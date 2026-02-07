# General Project Context

## API Contract

Pydantic models in `api/schemas.py` and `api/models.py` are the source of truth for the API contract.

When working on backend routes, reference those files for accurate type information and endpoint contracts.

## Pre-commit

Before committing and pushing code, **always** run pre-commit locally to catch lint, format, and type errors early:

```bash
cd api && uv run pre-commit run --all-files
```

If pre-commit is not yet installed as a git hook, install it first:

```bash
cd api && uv run pre-commit install
```

Do not commit or push code that fails pre-commit checks.
