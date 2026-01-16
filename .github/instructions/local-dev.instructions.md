---
applyTo: 'docker-compose.yml, .env*, **/Dockerfile'
---

# Local Development Setup

## Quick Start

1. Open in VS Code → `F1` → "Dev Containers: Reopen in Container"
2. Set env vars (see below)
3. Run & Debug → "Full Stack: API + Frontend"

## Environment Variables

**API** (`api/.env`):
```bash
CLERK_SECRET_KEY=sk_test_...
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/learn_to_cloud
```

**Frontend** (`frontend/.env.local`):
```bash
VITE_CLERK_PUBLISHABLE_KEY=pk_test_...
VITE_API_URL=http://localhost:8000
```

## URLs

| Service | URL |
|---------|-----|
| Frontend | http://localhost:3000 |
| API | http://localhost:8000 |
| API Docs | http://localhost:8000/docs |

## Common Fixes

```bash
# Port in use
pkill -f "uvicorn main:app" && pkill -f "vite"

# Start database
docker-compose up -d db

# Module not found - use venv python
cd api && .venv/bin/python -m uvicorn main:app --reload
```
