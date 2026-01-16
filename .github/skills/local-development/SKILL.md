---
name: local-development
description: Set up and run the Learn to Cloud application locally for development. Use when starting the dev environment, debugging startup issues, configuring environment variables, or troubleshooting database/port problems.
---

# Local Development

## Quick Start (Dev Container)

1. Open folder in VS Code
2. `F1` → "Dev Containers: Reopen in Container"
3. Configure environment variables (see below)
4. Use Run and Debug panel → "Full Stack: API + Frontend"

## Environment Variables

**API** (`api/.env`):
```bash
# Required - get from Clerk dashboard
CLERK_SECRET_KEY=sk_test_...

# Auto-configured in dev container
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/learn_to_cloud
```

**Frontend** (`frontend/.env.local`):
```bash
# Required - get from Clerk dashboard
VITE_CLERK_PUBLISHABLE_KEY=pk_test_...

# API URL (defaults to localhost:8000)
VITE_API_URL=http://localhost:8000
```

## Running Services

**Using VS Code debugger (recommended):**
- `Ctrl+Shift+D` / `Cmd+Shift+D` → Select launch config

**Manual commands:**

API:
```bash
cd api
.venv/bin/python -m uvicorn main:app --reload --port 8000
```

Frontend:
```bash
cd frontend
npm run dev
```

## Service URLs

| Service | URL |
|---------|-----|
| Frontend | http://localhost:3000 |
| API | http://localhost:8000 |
| API Docs | http://localhost:8000/docs |
| Health check | http://localhost:8000/health |

## Database

Start PostgreSQL:
```bash
docker-compose up -d db
```

Database URL: `postgresql://postgres:postgres@localhost:5432/learn_to_cloud`

## Common Issues

**Port already in use:**
```bash
pkill -f "uvicorn main:app"  # Kill API
pkill -f "vite"               # Kill frontend
```

**Module not found:**
- Use `.venv/bin/python` not system python
- Run `uv sync` in api directory

**Database connection failed:**
- Ensure Docker is running
- Run `docker-compose up -d db`

**Clerk authentication errors:**
- Verify CLERK_SECRET_KEY is set
- Check key matches your Clerk application

## Package Management

**Python (API):**
```bash
cd api
uv sync              # Install dependencies
uv add <package>     # Add new package
```

**Node.js (Frontend):**
```bash
cd frontend
npm install          # Install dependencies
npm install <pkg>    # Add new package
```

## Running Tests

```bash
cd api
.venv/bin/python -m pytest -v
```
