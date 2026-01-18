# Docker Strategy

This document explains the Docker configuration for the Learn to Cloud application.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                         PRODUCTION                                   │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│   api/Dockerfile  ──▶  Azure Container Registry  ──▶  Container Apps │
│                                                                      │
│   frontend/       ──▶  Vite Build  ──▶  Azure Static Web Apps (CDN) │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│                       LOCAL DEVELOPMENT                              │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│   docker compose up db     ──▶  PostgreSQL (postgres:16-alpine)     │
│   npm run dev              ──▶  Vite dev server (frontend/)         │
│   uvicorn main:app         ──▶  FastAPI (api/)                      │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

**Key Decision:** The API is containerized; the frontend is NOT. The frontend deploys as static files to Azure Static Web Apps for CDN performance.

---

## Docker Files

### 1. `docker-compose.yml` — Local Development

**Purpose:** Provides PostgreSQL database and optional multi-worker API testing.

| Service | Image | Port | Purpose |
|---------|-------|------|---------|
| `db` | `postgres:16-alpine` | 5432 | Local PostgreSQL database |
| `api-multiworker` | Builds `api/Dockerfile` | 8000 | Test migration race conditions |

**Usage:**

```bash
# Start only the database (recommended for local dev)
docker compose up -d db

# Test multi-worker migrations (for debugging race conditions)
docker compose up db api-multiworker --build
```

**When to use `api-multiworker`:**
- Testing that database migrations work correctly with multiple Uvicorn workers
- Reproducing race condition bugs that only occur in production (2+ workers)
- The service uses `RUN_MIGRATIONS_ON_STARTUP=true` to trigger migrations

---

### 2. `api/Dockerfile` — API Container (Local + Production)

**Purpose:** Multi-stage build for the FastAPI backend.

| Stage | Base Image | Purpose |
|-------|------------|---------|
| builder | `python:3.13-slim` | Install dependencies with `uv` |
| runtime | `python:3.13-slim` | Minimal production image |

**Key Features:**

| Feature | Configuration |
|---------|---------------|
| Package manager | `uv` (fast Python dependency resolver) |
| Init system | `tini` (proper signal handling, zombie reaping) |
| Non-root user | `appuser` (security best practice) |
| Workers | 2 Uvicorn workers |
| Health check | `GET /health` |

**Build Command:**

```bash
# Must use repo root as context (content is copied from frontend/)
docker build -f api/Dockerfile -t api .
```

**Why repo root context?** The Dockerfile copies content from outside the `api/` folder:

```dockerfile
COPY --chown=appuser:appuser frontend/public/content /app/content
```

---

### 3. `.dockerignore` — Build Optimization

**Purpose:** Excludes unnecessary files from the Docker build context.

**Location:** Repository root only (Docker reads `.dockerignore` from the build context root).

**Key Exclusions:**

| Pattern | Reason |
|---------|--------|
| `**/.venv/`, `**/node_modules/` | Dependencies (reinstalled in container) |
| `.git/` | Version control history |
| `infra/` | Terraform files not needed in image |
| `**/*.pyc`, `**/__pycache__/` | Python bytecode |
| `.env` | Secrets (injected at runtime) |

---

## Content Strategy

Content files (`frontend/public/content/`) are **baked into the API image** at build time:

```dockerfile
COPY --chown=appuser:appuser frontend/public/content /app/content
```

**Why?**
- API serves content via `/content/*` endpoints
- Content changes require an API image rebuild and deployment
- Ensures API and content versions are always in sync

See [content-strategy.md](content-strategy.md) for details.

---

## Production Deployment (CI/CD)

The GitHub Actions workflow (`deploy.yml`) handles production builds:

1. **Pull existing image** — Cache warming with `:latest` tag
2. **Build new image** — Tag with git commit SHA
3. **Smoke test** — Run container locally, check `/health`
4. **Security scan** — Trivy scans for vulnerabilities
5. **Push to ACR** — Both `:sha` and `:latest` tags
6. **Deploy** — Update Azure Container Apps revision

**Weekly Security Rebuilds:**
- `weekly-rebuild.yml` runs every Sunday at 6 AM UTC
- Pulls fresh base images (security patches)
- Bypasses all cached layers

---

## What's NOT Containerized

| Component | Deployment | Reason |
|-----------|------------|--------|
| Frontend | Azure Static Web Apps | CDN edge caching, no server needed |
| Database | Azure PostgreSQL Flexible Server | Managed service with backups |

---

## Quick Reference

| Task | Command |
|------|---------|
| Start local database | `docker compose up -d db` |
| Stop local database | `docker compose down` |
| Test multi-worker migrations | `docker compose up db api-multiworker --build` |
| Build API image locally | `docker build -f api/Dockerfile -t api .` |
| Run API container locally | `docker run -p 8000:8000 -e DATABASE_URL=... api` |
| View database data | `docker compose exec db psql -U postgres -d learn_to_cloud` |
