# Learn to Cloud App

A web application for tracking your progress through the [Learn to Cloud](https://learntocloud.guide) guide.

> **Note:** This is a closed-source project. All rights reserved.

## Features

- 📚 All 7 phases of the Learn to Cloud curriculum
- ✅ Progress tracking with steps, questions, and hands-on projects
- 🏆 Badges and achievements for completing phases
-  Certificates for phase completion
- 🔐 Authentication via Clerk
- 📊 Dashboard with progress visualization
- 🐙 GitHub integration for project submissions

## Tech Stack

| Layer | Technology |
|-------|------------|
| **Backend** | Python 3.13+, FastAPI, SQLAlchemy (async), PostgreSQL |
| **Frontend** | React 19, Vite, TypeScript, Tailwind CSS v4 |
| **Auth** | Clerk |
| **Infra** | Azure Container Apps, Azure PostgreSQL, Terraform |
| **CI/CD** | GitHub Actions |

## Quick Start

### Prerequisites

- Python 3.13+ with [uv](https://docs.astral.sh/uv/)
- Node.js 20+
- Docker
- [Clerk](https://clerk.com) account

### Local Development

#### Using Devcontainer
If you're using the VS Code Devcontainer, the environment is mostly auto-configured in post-create.

**1. Reload devcontainer** in VS Code (if not already open)

**2. Edit environment variables** — Update `api/.env` with your own values (Clerk keys, Google API key, etc.)

**3. Start the services:**

```bash
# Terminal 1: API
cd api
docker compose up -d db                # Start database
.venv/bin/alembic upgrade head         # Run migrations
.venv/bin/python -m uvicorn main:app --reload --port 8000

# Terminal 2: Frontend
cd frontend
npm run dev
```

#### Local Setup (without Devcontainer)
**1. Start the database (Docker)**

```bash
docker compose up -d db
```

**2. API setup (terminal 1)**

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

**3. Frontend setup (terminal 2)**

```bash
cd frontend
npm install
cp .env.example .env.local  # Add VITE_CLERK_PUBLISHABLE_KEY
npm run dev
```

**Notes:**
- The API does not start Postgres for you. Run `docker compose up -d db` first.
- Manage the database with `docker compose start db` / `docker compose stop db`.

| Service | URL |
|---------|-----|
| Frontend | http://localhost:3000 |
| API | http://localhost:8000 |
| API Docs | http://localhost:8000/docs |

See [CONTRIBUTING.md](CONTRIBUTING.md) for detailed development guide.

## Project Structure

```
├── api/                  # FastAPI backend
│   ├── main.py           # App entry point
│   ├── models.py         # SQLAlchemy models
│   ├── schemas.py        # Pydantic schemas
│   ├── routes/           # API endpoints
│   ├── services/         # Business logic
│   ├── repositories/     # Database queries
│   ├── core/             # Config, auth, database
│   └── tests/
├── frontend/             # React + Vite frontend
│   ├── src/
│   │   ├── components/
│   │   ├── pages/
│   │   └── lib/          # API client, hooks
│   └── public/
│       └── content/      # Phase/topic JSON content
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
