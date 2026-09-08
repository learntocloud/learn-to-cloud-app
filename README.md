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
| **Verification** | Sequential API background worker + shared Python package |
| **Frontend** | HTMX, Jinja2 templates, Alpine.js, Tailwind CSS v4 |
| **Auth** | GitHub OAuth (Authlib) |
| **Infra** | Azure Container Apps, Azure PostgreSQL, Terraform |
| **CI/CD** | GitHub Actions |

GitHub login establishes revocable, PostgreSQL-backed sessions. See
[Authentication and sessions](docs/contributing.md#authentication-and-sessions)
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

`uv` installs the required Python 3.13 runtime. Frontend, verification,
infrastructure, and agent workflows need additional optional tools documented
in the [Contributing Guide](docs/contributing.md#tooling-by-workflow).

#### Local Development

**1. Start local dependencies (Docker)**

```bash
docker compose up -d db aspire-dashboard
```

**2. Install Python dependencies**

This project is a single uv workspace. One command installs the API and shared
packages into one virtual environment:

```bash
uv sync --all-packages --locked
cp api/.env.example api/.env  # Create environment config (edit if needed)
```

Run database migrations:

```bash
cd api && uv run alembic upgrade head && cd ..
```

Start the API:

```bash
cd api && uv run python -m uvicorn learn_to_cloud.main:app --reload --port 8000
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
| API Docs | http://localhost:8000/docs (requires `DEBUG=true`) |
| PostgreSQL | `127.0.0.1:55432` (user: `postgres`, password: `postgres`) |
| Aspire Dashboard | http://localhost:18888 |

## Project Structure

```
├── api/                  # FastAPI backend (serves HTML + JSON API)
│   ├── src/
│   │   └── learn_to_cloud/
│   │       ├── main.py       # App entry point
│   │       ├── routes/       # API + page endpoints
│   │       ├── services/     # Business logic
│   │       ├── repositories/ # Database queries
│   │       ├── core/         # Config, auth, database
│   │       ├── templates/    # Jinja2 templates (HTMX)
│   │       └── static/       # CSS, JS, images
│   └── tests/
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
Published architecture and operations docs are available on
[GitHub Pages](https://learntocloud.github.io/learn-to-cloud-app/).

## Deployment

Pushes to `main` select deployment work by changed paths:

- Application changes build and validate the API and migration images, run
  migrations, update the API, and verify production in one deployment job.
- Infrastructure changes call `infra-deploy.yml` to plan and apply Terraform,
  then verify production without building images, running migrations, or updating
  the API image. Terraform can still update the API's configuration.
- Combined changes apply infrastructure before the application deployment.

`app-deploy.yml` remains the single production entry point so combined releases
are ordered and production deployments do not overlap. Application-only releases
read Terraform outputs but do not plan or apply infrastructure. CI is unchanged.
The legacy Functions shutdown remains a temporary prerequisite until the
verification-worker cutover is confirmed complete.

For manual runs of **Application Deploy**, choose `application` (the default),
`infrastructure`, or `all`. A manual **Infrastructure Deploy** run remains
plan-only. Use `all` for coordinated database/identity changes or recovery that
also requires migrations and an application rollout; infrastructure-only mode is
not a database bootstrap procedure.

After a failed deployment, fix and rerun it before shipping another release.
Path selection describes the current push, not everything since the last
successful deployment. Do not use an old workflow run as an image-only rollback.

## License

MIT License. See [LICENSE](LICENSE).
