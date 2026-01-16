---
name: api-dev
description: Develop the FastAPI backend: add endpoints, modify models, run tests. Use when creating routes, updating models, writing tests, or debugging API issues.
---

# Python API Development

## Running the API

```bash
cd api
.venv/bin/python -m uvicorn main:app --reload --port 8000
```

Or use VS Code debugger: `Ctrl+Shift+D` → "API: FastAPI (uvicorn)"

## API URLs

| URL | Purpose |
|-----|---------|
| http://localhost:8000/docs | Swagger UI |
| http://localhost:8000/health | Liveness check |
| http://localhost:8000/ready | Readiness check |

## Project Structure

```
api/
├── main.py              # FastAPI app entry
├── routes/              # API endpoints
│   ├── activity.py
│   ├── certificates.py
│   ├── github.py        # Hands-on submissions
│   ├── health.py
│   ├── questions.py
│   ├── steps.py
│   ├── users.py
│   └── webhooks.py
├── shared/              # Shared modules
│   ├── auth.py          # Clerk authentication
│   ├── badges.py        # Badge computation
│   ├── certificates.py  # Certificate generation
│   ├── config.py        # Settings/env vars
│   ├── database.py      # SQLAlchemy setup
│   ├── hands_on_verification.py
│   ├── github_hands_on_verification.py
│   ├── llm.py           # LLM grading
│   ├── models.py        # SQLAlchemy models
│   ├── progress.py      # Progress calculation
│   ├── schemas.py       # Pydantic schemas
│   └── streaks.py       # Streak calculation
└── tests/
```

## Package Management

```bash
cd api
uv sync              # Install dependencies
uv add <package>     # Add package
uv remove <package>  # Remove package
```

## Running Tests

```bash
cd api
.venv/bin/python -m pytest -v          # All tests
.venv/bin/python -m pytest -v -k test_name  # Specific test
```

## Adding a New Endpoint

1. Create or edit route file in `routes/`
2. Add router to `main.py` if new file
3. Add Pydantic schemas to `shared/schemas.py`
4. Add tests in `tests/`

Example route:
```python
from fastapi import APIRouter
from shared.auth import UserId
from shared.database import DbSession

router = APIRouter(prefix="/api/example", tags=["example"])

@router.get("/")
async def get_example(user_id: UserId, db: DbSession):
    return {"message": "Hello"}
```

## Database Operations

**Models** in `shared/models.py`:
- `User` - Synced from Clerk
- `Submission` - Hands-on submissions (URLs, CTF tokens, etc.)
- `QuestionAttempt` - Question attempts
- `StepProgress` - Completed steps
- `UserActivity` - Activity tracking
- `Certificate` - Issued certificates

**Common patterns:**
```python
# Query
result = await db.execute(select(User).where(User.id == user_id))
user = result.scalar_one_or_none()

# Insert
db.add(new_record)
await db.commit()

# Update
user.field = new_value
await db.commit()
```

## Authentication

Uses Clerk. Get authenticated user ID:
```python
from shared.auth import UserId

@router.get("/endpoint")
async def endpoint(user_id: UserId):
    # user_id is the Clerk user ID string
    pass
```

## Common Issues

**Module not found:**
```bash
# Use venv python, not system python
.venv/bin/python -m uvicorn main:app --reload
```

**Port in use:**
```bash
pkill -f "uvicorn main:app"
```

**Database errors:**
```bash
docker-compose up -d db  # Ensure DB is running
```

**Import errors after changes:**
- Restart uvicorn (auto-reload may miss some changes)
- Check `__init__.py` exports
