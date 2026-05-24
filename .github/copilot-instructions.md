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

When a migration updates row values AND modifies check constraints, always drop the constraints first, then update rows, then add new constraints. Postgres enforces check constraints during the UPDATE, so updating rows before dropping the old constraint will fail if the new value isn't in the old constraint's allowed list.

## Quality Gates

Do not push unless all of the following pass:

- `cd api && uv run ruff check . ../packages/learn-to-cloud-shared`
- `cd api && uv run ruff format --check . ../packages/learn-to-cloud-shared`
- `cd api && uv run ty check --exclude scripts --exclude tests .`
- `cd packages/learn-to-cloud-shared && uv run ty check --exclude tests .`
- `cd api && uv run pytest tests/`
- `cd packages/learn-to-cloud-shared && uv run pytest tests/`
- `cd apps/verification-functions && uv run ruff check . && uv run ruff format --check . && uv run ty check . && uv run python -c "import function_app"`

Do not write `# noqa`, `type: ignore`, or ty/ruff suppression comments unless absolutely unavoidable.

### Validation Workflow (run continuously, not just at the end)

The Quality Gates commands above are the source of truth — **not `prek run --all-files`**. `prek --all-files` only inspects git-tracked files, so newly-created files (new migrations, new modules, new tests) get silently skipped. Relying on prek alone will let real ruff/ty violations slip through until the commit hook fires.

Follow this loop:

1. **After every batch of edits**, run the explicit Quality Gates commands for the project(s) you touched. At minimum, run `ruff check`, `ruff format --check`, and `ty check`. Do this even if you only changed one file — it takes seconds.
2. **When creating new files**, either `git add` them first (so prek sees them) or run ruff/ty directly against the file path: `uv run ruff check path/to/new_file.py`.
3. **Before declaring work complete**, run the entire Quality Gates block from top to bottom, in addition to any test/dog-food steps. Treat any failure as blocking.
4. **Write code that respects ruff and ty by default** — match `line-length = 88`, prefer explicit imports, keep functions type-annotated, avoid unused imports/variables. Don't write code first and clean up later; getting it right the first time is faster.
5. **Long SQL or string literals in migrations** must respect `line-length = 88`. Break long `SELECT` / `INSERT` lists across multiple lines inside the SQL string — ruff lints the Python source, not the SQL.

If a check fails, fix it before moving on. Do not batch lint fixes for the end of the task.

## Research
When asked to research, or If you need to research something that is azure related, use azure-skills plugin. If you need more info or another topic, use firecrawl or tavily (whichever one is installed) and or context7. The built in web search tool should not be used for research purposes unless no other options are available.
