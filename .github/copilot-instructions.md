# Copilot Instructions

## Branching

Always work on a feature branch — never commit directly to `main`.

Use descriptive prefixes:

- `fix/` — bug fixes (e.g., `fix/deterministic-pr-grading`)
- `feat/` — new features (e.g., `feat/phase4-verification`)
- `chore/` — maintenance, deps, docs (e.g., `chore/update-dependencies`)
- `refactor/` — code restructuring (e.g., `refactor/auth-middleware`)

Workflow:

1. Create a branch from `main` before making changes
2. Commit and push to the branch
3. Open a Pull Request to merge into `main`
4. Never force-push to `main` or commit directly to it

## Code Comments and Docstrings

Keep docstrings short and useful. One line is enough for most functions.

- Don't restate the function name or parameters when they're obvious
- Don't document implementation history ("removed X", "no longer uses Y")
- Don't add `Args:` / `Returns:` blocks when the types and names are self-explanatory
- Only comment code that needs clarification — skip the obvious

## Database Migrations

Never edit alembic migration files after they've been created. They are immutable historical records that may have already run in production. If a migration needs correcting, create a new migration instead.

## Quality Gates

Do not push unless all of the following pass:

- `cd api && uv run ruff check . ../packages/learn-to-cloud-shared`
- `cd api && uv run ruff format --check . ../packages/learn-to-cloud-shared`
- `cd api && uv run ty check --exclude scripts --exclude tests .`
- `cd packages/learn-to-cloud-shared && uv run ty check --exclude tests .`
- `cd api && uv run pytest tests/ ../packages/learn-to-cloud-shared/tests`
- `cd apps/verification-functions && uv run ruff check . && uv run ruff format --check . && uv run ty check . && uv run python -c "import function_app"`

Do not write `# noqa`, `type: ignore`, or ty/ruff suppression comments unless absolutely unavoidable.
