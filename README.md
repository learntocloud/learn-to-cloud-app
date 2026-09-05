# Learn to Cloud App

A web application for tracking your progress through the [Learn to Cloud](https://learntocloud.guide) guide.

> **Note:** This project is open source under the MIT License.

## Features

- 📚 All 8 phases of the Learn to Cloud curriculum
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

GitHub login establishes signed-cookie sessions. See
[Authentication and sessions](docs/contributing.md#authentication-and-sessions)
for route dependencies, login redirects, and logout limitations.

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
docker compose up -d db azurite dts aspire-dashboard
```

**2. Install Python dependencies**

This project is a single uv workspace. One command installs the API, the
shared package, and the verification Functions worker into one shared
virtual environment:

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

Start the verification worker when testing hands-on submissions:

```bash
cd apps/verification-functions
uv run func start --port 7071
```

Or install the workspace's recommended Azure Functions extension and use
VS Code's **"API + Verification"** compound launch configuration. It starts
Core Tools and attaches the Python debugger to the Functions worker.

**Notes:**
- The API does not start local dependencies for you. Run `docker compose up -d db azurite dts` first.
- Verification submissions require the Durable Functions host on port `7071`.
- Stop the Functions host with `Ctrl+C`, or `kill -INT <pid>` if you started it in
  the background. The Core Tools host installs no `SIGTERM` handler, so a plain
  `kill` leaves it holding port `7071` and blocks the next run; `SIGINT` shuts it
  down in about a second and works on the `uv run` wrapper PID too.
- Manage dependencies with `docker compose start` / `docker compose stop`.

| Service | URL |
|---------|-----|
| App | http://localhost:8000 |
| API Docs | http://localhost:8000/docs (requires `DEBUG=true`) |
| PostgreSQL | `127.0.0.1:55432` (user: `postgres`, password: `postgres`) |
| Durable Task Scheduler Dashboard | http://localhost:8082 |
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
Published architecture and operations docs are available on
[GitHub Pages](https://learntocloud.github.io/learn-to-cloud-app/).

## Deployment

Push to `main` triggers automated deployment via GitHub Actions → Terraform → Azure.
Production verification uses the GitHub Actions secret `TF_VAR_github_token`
to populate the `GITHUB__TOKEN` environment variable used by verification jobs.

## License

MIT License. See [LICENSE](LICENSE).
