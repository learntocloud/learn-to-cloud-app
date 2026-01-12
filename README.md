# Learn to Cloud App

A web application for tracking your progress through the [Learn to Cloud](https://learntocloud.guide) guide.

> **Note:** This is a closed-source project. All rights reserved.

## Features

- 📚 All 6 phases of the Learn to Cloud curriculum
- ✅ Progress tracking for topics and checklist items
- 🔐 Authentication via Clerk
- 📊 Dashboard with overall progress visualization
- 🐙 GitHub integration for project submissions
- ☁️ Deployable to Azure (Container Apps + PostgreSQL)

## Tech Stack

### Backend
- **Python 3.13+** with **FastAPI**
- **Uvicorn** ASGI server
- **SQLAlchemy** (async) for database ORM
- **PostgreSQL** (production) / **SQLite** (development)
- **Clerk** for authentication
- **uv** for package management

### Frontend
- **Next.js 16** with App Router
- **TypeScript**
- **Tailwind CSS v4**
- **Clerk** for authentication UI

### Infrastructure
- **Azure Container Apps** - Backend and frontend hosting
- **Azure Database for PostgreSQL** (Flexible Server) - Production database
- **Azure Application Insights** - Monitoring
- **Docker** - Containerization

## Local Development

### Prerequisites
- Python 3.13+
- Node.js 20+
- [uv](https://docs.astral.sh/uv/) - Python package manager
- [Clerk](https://clerk.com) account
- Docker (optional, for containerized development)

### 1. Backend setup (FastAPI)

```bash
cd api

# Create and activate virtual environment
uv venv
source .venv/bin/activate

# Install dependencies
uv sync

# Copy and edit environment variables
cp .env.example .env
# Edit .env with your Clerk keys and database settings

# Run FastAPI locally
uvicorn main:app --reload --port 7071
```

Backend will be available at http://localhost:7071

### 2. Frontend setup

```bash
cd frontend

# Install dependencies
npm install

# Copy environment variables
cp .env.example .env.local
# Edit .env.local with your Clerk keys

# Run development server
npm run dev
```

Frontend will be available at http://localhost:3000

### 3. Configure Clerk

1. Create a Clerk application at https://dashboard.clerk.com
2. Get your API keys:
   - `CLERK_SECRET_KEY` (backend)
   - `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` (frontend)
3. Set up webhook:
   - Endpoint: `http://localhost:7071/webhooks/clerk`
   - Events: `user.created`, `user.updated`, `user.deleted`
   - Get `CLERK_WEBHOOK_SIGNING_SECRET`

### 4. Docker Compose (Alternative)

Run both services with Docker:

```bash
docker-compose up --build
```

## Azure Deployment

### Using Azure Developer CLI (Recommended)

```bash
# Login to Azure
azd auth login

# Initialize environment (first time only)
azd init

# Provision infrastructure and deploy
azd up
```

You'll be prompted for secure parameters (PostgreSQL password, Clerk keys).

## API Endpoints

| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| GET | `/health` | Health check | No |
| GET | `/ready` | Readiness check (init complete + DB reachable) | No |
| GET | `/phases` | List all phases | No |
| GET | `/phases/{id}` | Get phase by ID | No |
| GET | `/p/{slug}` | Get phase by slug | No |
| GET | `/p/{phase}/{topic}` | Get topic by slug | No |
| GET | `/user/phases` | Phases with progress | Yes |
| GET | `/user/p/{slug}` | Phase with full progress | Yes |
| GET | `/user/p/{phase}/{topic}` | Topic with progress | Yes |
| GET | `/user/dashboard` | User dashboard data | Yes |
| POST | `/checklist/{id}/toggle` | Toggle checklist item | Yes |
| POST | `/github/submit` | Submit GitHub project | Yes |
| POST | `/webhooks/clerk` | Clerk webhook handler | Svix |

### Health vs readiness

- **`/health`** is a fast liveness endpoint. It does **not** depend on the database.
- **`/ready`** is a readiness endpoint. It returns **200** only after:
   - background initialization completed successfully, and
   - the database is reachable.

In Azure Container Apps, the API container uses:
- **Startup + liveness probes**: `/health`
- **Readiness probe**: `/ready`

Local quick check:

```bash
curl -i http://localhost:7071/health
curl -i http://localhost:7071/ready
```

## Project Structure

```
learn-to-cloud-app/
├── api/
│   ├── main.py              # FastAPI application entry point
│   ├── Dockerfile           # API container definition
│   ├── pyproject.toml       # uv/Python dependencies
│   ├── routes/
│   │   ├── __init__.py      # Router exports
│   │   ├── checklist.py     # Checklist toggle endpoints
│   │   ├── github.py        # GitHub submission endpoints
│   │   ├── health.py        # Health check endpoint
│   │   ├── users.py         # User progress endpoints
│   │   └── webhooks.py      # Clerk webhook handler
│   └── shared/
│       ├── __init__.py      # Module exports
│       ├── auth.py          # Clerk authentication
│       ├── config.py        # Settings
│       ├── database.py      # DB connection
│       ├── github.py        # GitHub API integration
│       ├── models.py        # SQLAlchemy models
│       ├── schemas.py       # Pydantic schemas
│       └── telemetry.py     # Azure Monitor integration
├── frontend/
│   ├── src/
│   │   ├── app/             # Next.js App Router pages
│   │   ├── components/      # React components
│   │   ├── lib/             # API client, types, hooks
│   │   └── proxy.ts         # Clerk auth proxy
│   ├── content/
│   │   └── phases/          # Phase and topic JSON content
│   ├── Dockerfile           # Frontend container definition
│   └── package.json
├── infra/
│   ├── main.bicep           # Subscription-level deployment
│   └── resources.bicep      # Resource definitions
├── docker-compose.yml       # Local development containers
└── azure.yaml               # Azure Developer CLI config
```

## License

This project is proprietary and closed source. All rights reserved.
