# Learn to Cloud App

A web application for tracking your progress through the [Learn to Cloud](https://learntocloud.guide) guide.

> **Note:** This is a closed-source project. All rights reserved.

## Features

- 📚 All 7 phases of the Learn to Cloud curriculum
- ✅ Progress tracking with steps, questions, and hands-on projects
- 🏆 Badges and achievements for completing phases
- 📜 Certificates for phase completion
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

### Prerequisites

- Python 3.13+ with [uv](https://docs.astral.sh/uv/)
- Node.js 20+ (for Tailwind CSS build)
- Docker (for PostgreSQL)

### Local Development

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
.venv/bin/python -m uvicorn main:app --reload --port 8000

# Windows
.venv\Scripts\python -m uvicorn main:app --reload --port 8000
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
│   ├── main.py           # App entry point
│   ├── models.py         # SQLAlchemy models
│   ├── schemas.py        # Pydantic schemas
│   ├── routes/           # API + page endpoints
│   ├── services/         # Business logic
│   ├── repositories/     # Database queries
│   ├── core/             # Config, auth, database
│   ├── templates/        # Jinja2 templates (HTMX)
│   ├── static/           # CSS, JS, images
│   └── tests/
├── content/              # Course content (YAML)
│   └── phases/           # Phase and topic definitions
├── infra/                # Terraform (Azure)
└── .github/
    ├── workflows/        # CI/CD
    ├── instructions/     # Copilot custom instructions
    └── skills/           # Copilot agent skills
```

## Deployment

Push to `main` triggers automated deployment via GitHub Actions → Terraform → Azure Container Apps.

## License

This project is proprietary and closed source. All rights reserved.
