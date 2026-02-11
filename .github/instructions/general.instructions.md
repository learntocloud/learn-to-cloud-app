# General Project Context

## API Contract

Pydantic models in `api/schemas.py` and `api/models.py` are the source of truth for the API contract.

When working on backend routes, reference those files for accurate type information and endpoint contracts.

## Pre-commit (prek)

Before committing and pushing code, **always** run prek locally to catch lint, format, and type errors early:

```bash
prek run --all-files
```

If prek is not yet installed as a git hook, install it first:

```bash
prek install
```

Do not commit or push code that fails prek checks.
