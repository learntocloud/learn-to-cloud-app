# Learn to Cloud App

A web application for tracking your progress through the [Learn to Cloud](https://learntocloud.guide) guide.

> **Note:** This project is open source under the MIT License.

## Features

- 📚 All 7 phases of the Learn to Cloud curriculum
- ✅ Progress tracking with steps, questions, and hands-on projects
- 🔐 Authentication via GitHub OAuth
- 📊 Dashboard with progress visualization
- 🐙 GitHub integration for project submissions

## Tech Stack

| Layer | Technology |
|-------|------------|
| **Backend** | Python 3.13+, FastAPI, SQLAlchemy (async), PostgreSQL |
| **Frontend** | HTMX, Jinja2 templates, Alpine.js, Tailwind CSS v4 |
| **Auth** | GitHub OAuth (Authlib) |
| **Infra** | Azure Container Apps, Azure PostgreSQL, Terraform |
| **CI/CD** | GitHub Actions |

## Quick Start

### Dev Container (Recommended — all platforms)

The fastest way to get started on **Windows (WSL), macOS, or Linux** is with VS Code Dev Containers. Everything — Python, Node, PostgreSQL, uv, pre-commit hooks — is configured automatically.

**Prerequisites:** [Docker Desktop](https://www.docker.com/products/docker-desktop/) and [VS Code](https://code.visualstudio.com/) with the [Dev Containers extension](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers).

> **Windows users:** Install and run Docker Desktop via [WSL 2](https://learn.microsoft.com/en-us/windows/wsl/install). Clone the repo inside your WSL filesystem for best performance.

1. Clone the repo and open it in VS Code
2. When prompted **"Reopen in Container"**, click it (or run `Dev Containers: Reopen in Container` from the command palette)
3. Wait for the container to build — this runs automatically:
   - Installs Python 3.13, Node 20, uv, Azure CLI, GitHub CLI
   - Creates a Python virtual environment and installs all dependencies
   - Starts PostgreSQL 16 (port 54320) and runs database migrations
   - Installs `prek` pre-commit hooks
   - Copies `.env.example` → `.env` if needed
4. Start the API:
   ```bash
   cd api && uv run uvicorn learn_to_cloud.main:app --reload --port 8000
   ```

| Service | URL |
|---------|-----|
| App | http://localhost:8000 |
| API Docs | http://localhost:8000/docs (requires `DEBUG=true` in `.env`) |
| PostgreSQL | `localhost:54320` (user: `postgres`, password: `postgres`) |

### Manual Setup (without Dev Container)

If you prefer not to use Dev Containers, you can set things up manually.

#### Prerequisites

- Python 3.13+ with [uv](https://docs.astral.sh/uv/)
- Node.js 20+ (for Tailwind CSS build)
- Docker (for PostgreSQL)

#### Local Development

**1. Start the database (Docker)**

```bash
docker compose up -d db
```

**2. API setup**

```bash
cd api
uv venv                    # Create virtual environment
uv sync                    # Install Python dependencies
cp .env.example .env       # Create environment config (edit if needed)
```

Run database migrations:

```bash
# macOS/Linux
.venv/bin/alembic upgrade head

# Windows
.venv\Scripts\alembic upgrade head
```

Start the API:

```bash
# macOS/Linux
.venv/bin/python -m uvicorn learn_to_cloud.main:app --reload --port 8000

# Windows
.venv\Scripts\python -m uvicorn learn_to_cloud.main:app --reload --port 8000
```

Or use VS Code's debugger with the **"API: FastAPI (uvicorn)"** launch configuration.

**Notes:**
- The API does not start Postgres for you. Run `docker compose up -d db` first.
- Manage the database with `docker compose start db` / `docker compose stop db`.

| Service | URL |
|---------|-----|
| App | http://localhost:8000 |
| API Docs | http://localhost:8000/docs (requires `DEBUG=true`) |

## Project Structure

```
├── api/                  # FastAPI backend (serves HTML + JSON API)
│   ├── src/
│   │   └── learn_to_cloud/
│   │       ├── main.py       # App entry point
│   │       ├── models.py     # SQLAlchemy models
│   │       ├── schemas.py    # Pydantic schemas
│   │       ├── routes/       # API + page endpoints
│   │       ├── services/     # Business logic
│   │       ├── repositories/ # Database queries
│   │       ├── core/         # Config, auth, database
│   │       ├── templates/    # Jinja2 templates (HTMX)
│   │       └── static/       # CSS, JS, images
│   └── tests/
├── content/              # Course content (YAML)
│   └── phases/           # Phase and topic definitions
├── infra/                # Terraform (Azure)
└── .github/
    ├── workflows/        # CI/CD
    ├── instructions/     # Copilot custom instructions
    └── skills/           # Copilot agent skills
```

## Contributing

See the [Contributing Guide](docs/contributing.md) for linting, testing, the dog-food QA agent, Copilot skills, and architecture conventions.

## Deployment

Push to `main` triggers automated deployment via GitHub Actions → Terraform → Azure Container Apps.
Production verification uses the GitHub Actions secret `TF_VAR_github_token`
to populate the Container App `GITHUB_TOKEN` environment variable.

## License

MIT License. See [LICENSE](LICENSE).
