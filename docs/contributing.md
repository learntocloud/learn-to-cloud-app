# Contributing Guide

## Development Setup

The devcontainer handles everything automatically — see the [README](../README.md) for Quick Start instructions.

## Linting, Formatting & Type Checking

```bash
cd api

# Lint + format + type-check
ruff check . && ruff format --check . && ty check

# Auto-fix lint issues
ruff check --fix .

# Pre-commit (runs all checks)
prek run --all-files
```

## Tests

```bash
cd api

pytest                  # all tests
pytest -m unit          # unit only
pytest -m integration   # integration only (needs DB)
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

- Async/await everywhere — no sync database calls
- Database models use `TimestampMixin` for `created_at`/`updated_at`
- Enums: `class MyEnum(str, PyEnum)` with `native_enum=False` in columns
- Config via `pydantic-settings` (`Settings` class in `core/config.py`)
- Production migrations run through an Azure Container Apps Job before API deployment
