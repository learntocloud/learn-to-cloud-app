# Learn to Cloud App

A web application for tracking your progress through the [Learn to Cloud](https://learntocloud.guide) guide.

> **Note:** This project is open source under the MIT License.

## Features

- 📚 All 8 phases of the Learn to Cloud curriculum
- ✅ Progress tracking with steps, questions, and hands-on projects
- 🔐 Authentication via GitHub OAuth
- 📊 Dashboard with progress visualization
- 🐙 GitHub integration for project submissions
- ⚙️ Background verification inside the API container

## Tech Stack

| Layer | Technology |
|-------|------------|
| **Backend** | Python 3.13+, FastAPI, SQLAlchemy (async), PostgreSQL |
| **Verification** | Sequential API background worker |
| **Frontend** | HTMX, Jinja2 templates, Alpine.js, Tailwind CSS v4 |
| **Auth** | GitHub OAuth (Authlib) |
| **Infra** | Azure Container Apps, Azure PostgreSQL, Terraform |
| **CI/CD** | GitHub Actions |

GitHub login establishes revocable, PostgreSQL-backed sessions. See
[Authentication and sessions](docs/authentication.md)
for route dependencies, login redirects, expiry, and logout guarantees.

## Quick Start

### WSL / Linux Setup

Development runs directly in WSL or Linux. On Windows, install
[WSL 2](https://learn.microsoft.com/en-us/windows/wsl/install), keep the clone
inside the WSL filesystem, and make Docker Desktop's WSL integration available
to that distribution.

#### Prerequisites

- Git
- [uv](https://docs.astral.sh/uv/)
- Docker with the Compose plugin
- Node.js 20+ for the full test suite (not required just to start the API)

`uv` installs the required Python 3.13 runtime. Frontend, verification,
infrastructure, and agent workflows need additional optional tools documented
in the [Contributing Guide](docs/contributing.md#tooling-by-workflow).

#### Local Development

**1. Start local dependencies (Docker)**

```bash
docker compose up -d db aspire-dashboard
```

**2. Install Python dependencies**

Install the app and its development tools into a virtual environment:

```bash
uv sync --locked
cp .env.example .env  # Create environment config (edit if needed)
```

Run database migrations:

```bash
uv run alembic upgrade head
```

Start the API:

```bash
uv run python -m uvicorn learn_to_cloud.main:app --reload --port 8000
```

Or use VS Code's debugger with the **"API: FastAPI (uvicorn)"** launch configuration.

The API starts verification automatically: one sequential background loop per
API process atomically claims attempts from PostgreSQL. No separate host,
external queue, or verification job is required. Attempts have an execution
timeout and overdue cleanup, with no workflow retries or checkpoints.

**Notes:**
- The API does not start local dependencies for you. Run `docker compose up -d db aspire-dashboard` first.
- Manage dependencies with `docker compose start` / `docker compose stop`.

| Service | URL |
|---------|-----|
| App | http://localhost:8000 |
| API Docs | http://localhost:8000/docs (enabled in development or with `WEB_SECURITY__ENABLE_DOCS=true`) |
| PostgreSQL | `127.0.0.1:55432` (user: `postgres`, password: `postgres`) |
| Aspire Dashboard | http://localhost:18888 |

## Project Structure

```
├── src/
│   └── learn_to_cloud/   # FastAPI app (serves HTML + JSON API)
│       ├── main.py       # App entry point
│       ├── routes/       # API + page endpoints
│       ├── services/     # Business logic
│       ├── core/         # Config, auth, database, telemetry
│       ├── repositories/ # Database access
│       ├── verification/ # Verification checks and engine
│       ├── content/      # Curriculum YAML and compiled JSON
│       ├── migrations/   # Alembic migrations (shipped in the package)
│       ├── templates/    # Jinja2 templates (HTMX)
│       └── static/       # CSS, JS, images
├── tests/                # pytest suite
├── scripts/              # Dev and operator scripts
├── docs/                 # Contributor docs
├── infra/                # Terraform (Azure)
├── Dockerfile            # API and migration images
├── pyproject.toml        # Dependencies, tool config, poe tasks
└── .github/
    ├── workflows/        # CI/CD
    ├── copilot-instructions.md # Copilot custom instructions
    └── skills/           # Copilot agent skills
```

## Contributing

Start with the [Contributing Guide](docs/contributing.md) for setup, quality
gates, and links to focused development guides.

## Deployment

CI runs on pull requests. Pushes to `main` deploy through two independent
pipelines, selected by changed paths:

- `app-deploy.yml` runs for application runtime changes (`src/`, `Dockerfile`,
  dependency manifests). It builds and pushes the API and migration images,
  runs migrations, updates the API, and verifies production. It reads Terraform
  outputs but never plans or applies infrastructure. Tests and documentation do
  not deploy.
- `infra-deploy.yml` runs for `infra/` changes. It plans and applies Terraform,
  then verifies production without building images or running migrations.

Ship infrastructure and application changes as separate pull requests: merge the
infrastructure change and let it deploy before merging application code that
depends on it.

A manual **Infrastructure Deploy** run is plan-only unless `apply` is selected.
A manual **Application Deploy** run redeploys the current `main`.

After a failed deployment, fix and rerun it before shipping another release.
Path selection describes the current push, not everything since the last
successful deployment. Do not use an old workflow run as an image-only rollback.

## License

MIT License. See [LICENSE](LICENSE).
