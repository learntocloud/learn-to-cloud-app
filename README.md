# Learn to Cloud App

A web application for tracking your progress through the [Learn to Cloud](https://learntocloud.guide) guide.

> **Note:** This project is open source under the MIT License.

## Features

- 📚 All 7 phases of the Learn to Cloud curriculum
- ✅ Progress tracking with steps, questions, and hands-on projects
- 🔐 Authentication via GitHub OAuth
- 📊 Dashboard with progress visualization
- 🐙 GitHub integration for project submissions
- ⚙️ Async verification jobs powered by Durable Functions

## Tech Stack

| Layer | Technology |
|-------|------------|
| **Backend** | Python 3.13+, FastAPI, SQLAlchemy (async), PostgreSQL |
| **Verification** | Azure Durable Functions + shared Python package |
| **Frontend** | HTMX, Jinja2 templates, Alpine.js, Tailwind CSS v4 |
| **Auth** | GitHub OAuth (Authlib) |
| **Infra** | Azure Container Apps, Azure Functions, Azure PostgreSQL, Terraform |
| **CI/CD** | GitHub Actions |

## Quick Start

### Dev Container (Recommended — all platforms)

The fastest way to get started on **Windows (WSL), macOS, or Linux** is with VS Code Dev Containers. Everything — Python, Node, PostgreSQL, uv, pre-commit hooks — is configured automatically.

**Prerequisites:** [Docker Desktop](https://www.docker.com/products/docker-desktop/) and [VS Code](https://code.visualstudio.com/) with the [Dev Containers extension](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers).

> **Windows users:** Install and run Docker Desktop via [WSL 2](https://learn.microsoft.com/en-us/windows/wsl/install). Clone the repo inside your WSL filesystem for best performance.

1. Clone the repo and open it in VS Code
2. When prompted **"Reopen in Container"**, click it (or run `Dev Containers: Reopen in Container` from the command palette)
3. Wait for the container to build — this runs automatically:
   - Installs Python 3.13, Node 20, uv, Azure CLI, GitHub CLI, Azure Functions Core Tools
   - Creates a Python virtual environment and installs all dependencies
   - Starts PostgreSQL 16, Azurite, Durable Task Scheduler emulator, and Aspire Dashboard
   - Runs database migrations
   - Installs `prek` pre-commit hooks
   - Copies `.env.example` → `.env` if needed
4. Start the API and verification worker:
    ```bash
    (cd api && uv run uvicorn learn_to_cloud.main:app --reload --port 8000)
    ```
   For verification submissions, also run the **"Verification: Durable Functions"**
   VS Code launch configuration, or use the **"API + Verification"** compound
   launch configuration.

| Service | URL |
|---------|-----|
| App | http://localhost:8000 |
| API Docs | http://localhost:8000/docs (requires `DEBUG=true` in `.env`) |
| PostgreSQL | `localhost:54320` (user: `postgres`, password: `postgres`) |
| Durable Task Scheduler Dashboard | http://localhost:8082 |
| Aspire Dashboard | http://localhost:18888 |

### Manual Setup (without Dev Container)

If you prefer not to use Dev Containers, you can set things up manually.

#### Prerequisites

- Python 3.13+ with [uv](https://docs.astral.sh/uv/)
- Node.js 20+ (for Tailwind CSS build)
- Docker (for PostgreSQL)

#### Local Development

**1. Start local dependencies (Docker)**

```bash
docker compose up -d db azurite dts aspire-dashboard
```

**2. API setup**

```bash
cd api
uv sync --locked  # Install API + shared Python dependencies
cd ..
cp api/.env.example api/.env  # Create environment config (edit if needed)
```

Run database migrations:

```bash
# macOS/Linux
cd api && uv run alembic upgrade head && cd ..

# Windows
cd api; uv run alembic upgrade head; cd ..
```

Start the API:

```bash
# macOS/Linux
cd api && uv run python -m uvicorn learn_to_cloud.main:app --reload --port 8000

# Windows
cd api; uv run python -m uvicorn learn_to_cloud.main:app --reload --port 8000
```

Or use VS Code's debugger with the **"API: FastAPI (uvicorn)"** launch configuration.

Start the verification worker when testing hands-on submissions:

```bash
cd apps/verification-functions
uv sync --locked
uv run func start --port 7071
```

Or use VS Code's **"API + Verification"** compound launch configuration.

**Notes:**
- The API does not start local dependencies for you. Run `docker compose up -d db azurite dts` first.
- Verification submissions require the Durable Functions host on port `7071`.
- Manage dependencies with `docker compose start` / `docker compose stop`.

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
│   │       ├── models.py     # Compatibility imports for shared models
│   │       ├── schemas.py    # Compatibility imports for shared schemas
│   │       ├── routes/       # API + page endpoints
│   │       ├── services/     # Business logic
│   │       ├── repositories/ # Database queries
│   │       ├── core/         # Config, auth, database
│   │       ├── templates/    # Jinja2 templates (HTMX)
│   │       └── static/       # CSS, JS, images
│   └── tests/
├── apps/
│   └── verification-functions/ # Durable Functions host for async verification jobs
├── packages/
│   └── learn-to-cloud-shared/  # Shared domain, repositories, verification logic, and content
├── infra/                # Terraform (Azure)
└── .github/
    ├── workflows/        # CI/CD
    ├── instructions/     # Copilot custom instructions
    └── skills/           # Copilot agent skills
```

## Contributing

See the [Contributing Guide](docs/contributing.md) for linting, testing, the dog-food QA agent, Copilot skills, and architecture conventions.

## Deployment

Push to `main` triggers automated deployment via GitHub Actions → Terraform → Azure.
Production verification uses the GitHub Actions secret `TF_VAR_github_token`
to populate the `GITHUB_TOKEN` environment variable used by verification jobs.

## License

MIT License. See [LICENSE](LICENSE).
