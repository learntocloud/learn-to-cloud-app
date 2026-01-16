---
applyTo: 'api/**/*.py'
---

# API Development

## Layered Architecture & Separation of Concerns

The API follows a **4-layer architecture** with clear separation of concerns:

```
┌─────────────────────────────────────────────────────────────┐
│                      main.py                                │
│            (App initialization, middleware, routing)        │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    ROUTES LAYER                             │
│                    routes/*.py                              │
│  • HTTP request/response handling                           │
│  • Input validation (via Pydantic schemas)                  │
│  • Authentication enforcement                               │
│  • Error → HTTP status code mapping                         │
│  • Calls services, returns Pydantic response models         │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                   SERVICES LAYER                            │
│                   services/*.py                             │
│  • All business logic and rules                             │
│  • Orchestrates multiple repositories                       │
│  • Raises domain exceptions (not HTTP exceptions)           │
│  • Returns dataclasses (not ORM models or Pydantic)         │
│  • Activity logging and progress tracking                   │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                 REPOSITORIES LAYER                          │
│                 repositories/*.py                           │
│  • All database queries (SQLAlchemy)                        │
│  • CRUD operations on single entities                       │
│  • Returns ORM models or primitives                         │
│  • No business logic                                        │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    CORE LAYER                               │
│                    core/*.py                                │
│  • config.py   - Environment settings (Pydantic Settings)   │
│  • database.py - Engine, sessions, Base model               │
│  • auth.py     - Clerk authentication, UserId dependency    │
│  • ratelimit.py - SlowAPI rate limiting                     │
│  • telemetry.py - Request timing, security headers          │
└─────────────────────────────────────────────────────────────┘
```

### Data Flow Example: Complete a Step

```
POST /api/steps/complete
         │
         ▼
┌─────────────────────────────────────────┐
│ routes/steps.py                         │
│  • Validates StepCompleteRequest schema │
│  • Gets user_id from auth dependency    │
│  • Calls complete_step() service        │
│  • Maps exceptions → HTTP status        │
│  • Returns StepProgressResponse         │
└─────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────┐
│ services/steps.py                       │
│  • Validates step is unlocked           │
│  • Checks step not already completed    │
│  • Creates StepProgressRepository       │
│  • Logs activity via ActivityRepository │
│  • Returns StepCompletionResult         │
└─────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────┐
│ repositories/progress.py                │
│  • StepProgressRepository.exists()      │
│  • StepProgressRepository.create()      │
│  • Raw SQLAlchemy queries               │
└─────────────────────────────────────────┘
```

### Layer Responsibilities

| Layer        | Does                                      | Does NOT                                |
|--------------|-------------------------------------------|-----------------------------------------|
| Routes       | HTTP handling, auth, schema validation    | Business logic, direct DB queries       |
| Services     | Business rules, orchestration, exceptions | SQL queries, HTTP responses             |
| Repositories | Database queries, CRUD operations         | Business logic, validation              |
| Core         | Config, auth, DB sessions, middleware     | Business logic, HTTP endpoints          |

### Data Transfer Objects

| Type             | Used In     | Purpose                                        |
|------------------|-------------|------------------------------------------------|
| Pydantic schemas | Routes      | Request validation, API responses              |
| Dataclasses      | Services    | Internal data transfer between layers          |
| ORM models       | Repositories| Database operations, returned to services      |

## Project Structure

```
api/
├── main.py           # FastAPI app initialization, lifespan, middleware
├── models.py         # SQLAlchemy ORM models (database tables)
├── schemas.py        # Pydantic schemas (API request/response)
├── routes/           # HTTP endpoints (thin, delegate to services)
├── services/         # Business logic (orchestrates repositories)
├── repositories/     # Database queries (single entity CRUD)
├── core/             # Infrastructure (config, auth, database, telemetry)
├── rendering/        # Specialized rendering (certificates)
└── tests/            # Unit and integration tests
```

## Running

```bash
cd api && .venv/bin/python -m uvicorn main:app --reload --port 8000
```

URLs: `/docs` (Swagger), `/health`, `/ready`

## Adding an Endpoint

1. Add Pydantic schemas in `schemas.py` (request/response)
2. Add repository methods in `repositories/` if new DB queries needed
3. Add service functions in `services/` with business logic
4. Add route in `routes/` that delegates to service
5. Register router in `main.py` if new file
6. Add tests in `tests/`

## Patterns

```python
# Route with auth (thin - delegates to service)
from core.auth import UserId
from core.database import DbSession
from schemas import MyRequest, MyResponse
from services.my_service import do_something, SomeBusinessError

@router.post("/endpoint", response_model=MyResponse)
async def endpoint(request: MyRequest, user_id: UserId, db: DbSession):
    try:
        result = await do_something(db, user_id, request.data)
        return MyResponse(id=result.id, status=result.status)
    except SomeBusinessError as e:
        raise HTTPException(status_code=400, detail=str(e))

# Service function (contains business logic)
@dataclass
class SomeResult:
    id: int
    status: str

async def do_something(db, user_id: str, data: str) -> SomeResult:
    repo = MyRepository(db)
    existing = await repo.get_by_user(user_id)
    if existing:
        raise SomeBusinessError("Already exists")
    record = await repo.create(user_id, data)
    return SomeResult(id=record.id, status="created")

# Repository (database queries only)
class MyRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_user(self, user_id: str) -> Model | None:
        result = await self.db.execute(
            select(Model).where(Model.user_id == user_id)
        )
        return result.scalar_one_or_none()
```

## Commands

```bash
uv sync                    # Install deps
uv add <pkg>               # Add package
.venv/bin/python -m pytest -v  # Run tests
```
