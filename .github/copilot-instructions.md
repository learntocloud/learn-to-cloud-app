# Learn to Cloud App - AI Coding Instructions

## Architecture Overview

This is a **fullstack learning platform** with two main services:

- **`api/`** - FastAPI backend (Python 3.13+, async SQLAlchemy, PostgreSQL/SQLite)
- **`frontend/`** - Next.js 16 with App Router (TypeScript, Tailwind CSS v4, React 19)

**Authentication**: Clerk handles both frontend auth (React components) and backend JWT verification. Users are synced to the database via Clerk webhooks (`api/routes/webhooks.py`).

**Data Flow**: Frontend → Clerk token in `Authorization` header → Backend validates via `UserId` dependency → SQLAlchemy async queries → PostgreSQL (Azure) or SQLite (local)

## Key Patterns

### Backend (FastAPI)

**Dependency Injection** - Use typed dependencies from `shared/`:
```python
from shared.auth import UserId  # Requires auth, returns user_id: str
from shared.database import DbSession  # AsyncSession for database access

async def my_endpoint(user_id: UserId, db: DbSession):
    # user_id is guaranteed authenticated
```

**Models & Schemas** - SQLAlchemy models in `shared/models.py`, Pydantic schemas in `shared/schemas.py`. Always use `model_config = ConfigDict(from_attributes=True)` for ORM compatibility.

**Route Organization** - Each route file in `api/routes/` defines a `router = APIRouter(prefix="/api/...")` and is included in `main.py`.

**Database Operations** - Use async patterns:
```python
result = await db.execute(select(Model).where(...))
item = result.scalar_one_or_none()
```

### Frontend (Next.js)

**Content System** - Learning phases/topics are JSON files in `frontend/content/phases/`. They're imported statically in `src/lib/content.ts`. Add new content there.

**API Calls** - All backend calls go through `src/lib/api.ts` with server-side auth via `auth()` from `@clerk/nextjs/server`.

**Progress Tracking** - Checklist items use IDs like `phase0-check1` or `phase1-topic1-check1`. The backend stores completion state in `ChecklistProgress`.

## Development Commands

```bash
# Backend (from /workspaces/learn-to-cloud-app/api)
.venv/bin/python -m uvicorn main:app --reload --port 8000

# Frontend (from /workspaces/learn-to-cloud-app/frontend)
npm run dev  # Port 3000

# Database (PostgreSQL for local dev)
docker-compose up -d db
```

**Use VS Code Run/Debug** for "Full Stack: API + Frontend" launch config.

## Environment Configuration

- **Backend**: `api/.env` (copy from `.env.example`) - requires `CLERK_SECRET_KEY`
- **Frontend**: `frontend/.env.local` - requires `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY`
- **Database**: SQLite by default (`database_url`), PostgreSQL via `postgres_*` env vars for Azure

## Critical Integration Points

1. **Clerk Webhooks** (`/api/webhooks/clerk`) - Syncs users on `user.created`, `user.updated`, `user.deleted`
2. **GitHub Submissions** - Validates repos/URLs against `GITHUB_REQUIREMENTS` in `shared/github.py`
3. **Azure Deployment** - Uses managed identity for PostgreSQL auth (no passwords in production)

## File Naming & Structure

- Backend routes: `api/routes/{resource}.py` → `/api/{resource}/...`
- Shared utilities: `api/shared/` (auth, config, database, models, schemas)
- Frontend pages: `frontend/src/app/[phaseSlug]/[topicSlug]/page.tsx` (dynamic routes)
- Content JSON: `frontend/content/phases/phase{N}/{topic-slug}.json`

## Testing & Debugging

- API docs at http://localhost:8000/docs (Swagger UI)
- Health endpoints: `/health` (liveness), `/ready` (database check)
- Rate limiting: 100/min default, stricter for external API calls (GitHub validation)
