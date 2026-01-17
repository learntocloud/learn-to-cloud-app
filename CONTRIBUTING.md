# Contributing

## Copilot Skills

This project uses [VS Code Agent Skills](https://code.visualstudio.com/docs/copilot/customization/agent-skills) to help Copilot assist with common tasks.

| Skill | Purpose | Usage |
|-------|---------|-------|
| `azure-logs` | Fetch Azure Container Apps logs | "Show me the API logs" |
| `cicd-debug` | Debug GitHub Actions deploy failures | "The deploy failed, help me fix it" |
| `commit-deploy` | Commit, push, and watch CI | "Commit these changes and watch the deploy" |
| `debug-progression` | Debug locked content, badges, streaks | "Why is phase 2 locked for this user?" |
| `query-db` | Query production PostgreSQL | "Find users with duplicate github usernames" |

Skills are in `.github/skills/*/SKILL.md`.

## Custom Instructions

Instructions in `.github/instructions/*.instructions.md` are automatically applied based on file patterns:

| Instruction | Applies To |
|-------------|------------|
| `api.instructions.md` | `api/**/*.py` |
| `frontend.instructions.md` | `frontend/**/*.{ts,tsx}` |
| `local-dev.instructions.md` | `docker-compose.yml`, `.env*`, `Dockerfile` |
| `python.instructions.md` | `**/*.py` |
| `terraform.instructions.md` | `infra/*.tf` |
| `cicd.instructions.md` | `.github/workflows/*.yml` |

## Development Workflow

### Running Locally

```bash
# API
cd api && .venv/bin/python -m uvicorn main:app --reload --port 8000

# Frontend
cd frontend && npm run dev
```

Or use VS Code's Run & Debug panel.

### Testing

```bash
cd api && .venv/bin/python -m pytest -v
```

### Testing Multi-Worker Scenarios

To test that migrations work correctly with multiple uvicorn workers (as in production):

```bash
docker compose down -v && docker compose up db api-multiworker
```

This runs the API with 2 workers and `RUN_MIGRATIONS_ON_STARTUP=true`. Both workers should start successfully and `/ready` should return 200.

### Pre-commit

```bash
pre-commit run --all-files
```

### Deploying

Push to `main` triggers the deploy workflow. Monitor with:

```bash
gh run list --workflow=deploy.yml --limit 1
gh run watch <run-id>
```
