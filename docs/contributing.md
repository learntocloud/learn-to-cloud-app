# Contributing Guide

## Development Setup

The devcontainer handles everything automatically — see the [README](../README.md) for Quick Start instructions.

## Linting, Formatting & Type Checking

```bash
cd api
uv run ruff check . ../packages/learn-to-cloud-shared
uv run ruff format --check . ../packages/learn-to-cloud-shared
uv run ty check --exclude scripts --exclude tests .
cd ..

cd packages/learn-to-cloud-shared
uv run ty check --exclude tests .
cd ../..

cd apps/verification-functions
uv run ruff check .
uv run ruff format --check .
uv run ty check .
cd ../..

# Auto-fix lint issues
cd api && uv run ruff check --fix . ../packages/learn-to-cloud-shared && cd ..

# Pre-commit (runs all checks)
prek run --all-files
```

## Tests

```bash
# API tests (run from api/)
cd api
uv run pytest tests/
uv run pytest tests/ -m unit
uv run pytest tests/ -m integration
cd ..

# Shared package tests (run from the shared package)
cd packages/learn-to-cloud-shared
uv run pytest tests/
cd ../..
```

- Tests use transactional rollback for isolation — no table recreation per test
- Mark tests with `@pytest.mark.unit` or `@pytest.mark.integration`
- Async fixtures use `@pytest_asyncio.fixture`

## Dog Food Agent (AI-Powered QA)

The project includes a **dog-food agent** — an AI-powered QA workflow that automatically starts the local API, opens a headless browser, and walks through every page checking for errors, broken UI, and console messages.

### How to run it

In VS Code Copilot Chat, type:

```
test our app
```

or invoke the agent directly with `@dog-food`. The agent will:

1. **Start the API** on port 8000 and verify `/health` + `/ready`
2. **Install Chrome** if needed (headless, `--no-sandbox` for devcontainers)
3. **Test all public pages** — Home, Curriculum, FAQ, Privacy, Terms, Status
4. **Toggle dark mode** and verify it works
5. **Authenticate** via a signed session cookie (no real GitHub OAuth needed)
6. **Test authenticated pages** — Dashboard, Account, Phase, Topic
7. **Toggle a learning step** checkbox and verify it persists
8. **Report results** as a structured summary with pass/fail for each page

### Prerequisites

Everything is pre-installed by the devcontainer (`on-create.sh`):
- Playwright MCP server + Chrome (configured in `.vscode/mcp.json`)
- System libraries for headless Chrome (installed in the `Dockerfile`)
- Database seeded with at least one user (via `scripts/dogfood_session.py`)

### Artifacts

Screenshots are saved to `.dogfood/` (gitignored). No artifacts pollute the repo.

### How it works under the hood

| Component | File |
|-----------|------|
| Agent instructions | `.github/agents/dog-food.agent.md` |
| MCP server config | `.vscode/mcp.json` |
| Session cookie generator | `scripts/dogfood_session.py` |
| Chrome system deps | `.devcontainer/Dockerfile` |
| Chrome + MCP install | `.devcontainer/on-create.sh` |

## Copilot Skills

The project ships several Copilot agent skills in `.github/skills/`:

| Skill | Trigger | What it does |
|-------|---------|--------------|
| `validate` | "validate" | Lint, format, type-check, start API, smoke test |
| `ship-it` | "ship it" | Run prek, commit, push, monitor deploy |
| `check-prod` | "check prod" | Check Azure health, errors, latency |
| `debug-deploy` | "debug deploy" | Diagnose CI/CD and Terraform failures |
| `query-prod-db` | "query prod db" | Run ad-hoc queries against production DB |

## Architecture

```
Routes (HTTP) → Services (Business Logic) → Repositories (Database)
```

- **Routes** handle HTTP concerns, dependency injection, and template rendering
- **Services** contain business rules — no HTTP knowledge
- **Repositories** execute queries — return ORM models or primitives

## Conventions

- Async/await everywhere -- no sync database calls
- Database models use `TimestampMixin` for `created_at`/`updated_at`
- Enums: `class MyEnum(str, PyEnum)` with `native_enum=False` in columns
- Config via `pydantic-settings` (`Settings` class in `core/config.py`)
- Production migrations run through an Azure Container Apps Job before API deployment

## Database Migrations

### Keep schema changes and code changes in separate PRs

A PR that adds a new migration should not also change app code that
depends on the new schema. Ship them as two PRs:

1. **Schema PR** -- contains only the migration file. Merges and deploys
   first so the new table/index/column exists in production.
2. **Code PR** -- uses the new schema (e.g., `ON CONFLICT` against a new
   index, queries on a new column). Merges after the schema PR has
   deployed successfully.

Why: if a migration fails silently (or gets rolled back), the old app
code is still running. If that old code already depends on the new
schema, users see 500 errors. Keeping them separate means the old code
keeps working against the old schema.

It's fine to bundle them in one PR when the code change is purely
additive and the old code path doesn't break without the new schema
(e.g., adding a nullable column that nothing reads yet).

See [docs/migrations.md](migrations.md) for more on how migrations work.

## Editing curriculum content

Curriculum (phases, topics, steps, hands-on requirements) lives in
packaged YAML under
`packages/learn-to-cloud-shared/src/learn_to_cloud_shared/content/phases/`.
To change it:

1. Edit the YAML files. The deploy syncs them into Postgres -- no
   migration needed for content changes.
2. Validate locally:
   ```bash
   cd packages/learn-to-cloud-shared
   uv run python scripts/validate_content.py
   ```
3. Open a PR. CI runs the same validators.

See [`docs/curriculum.md`](curriculum.md) for the full architecture
(YAML-authoritative, deploy-time sync to Postgres, UUID FKs from
user state to curriculum). Schema changes to the curriculum tables
themselves are normal Alembic migrations; content changes go through
the sync.
