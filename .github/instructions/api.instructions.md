---
applyTo: 'api/**/*.py'
---

# API Development

## Project Structure

```
api/
├── main.py           # FastAPI app entry
├── models.py         # SQLAlchemy models
├── schemas.py        # Pydantic schemas
├── routes/           # API endpoints
├── services/         # Business logic
├── repositories/     # Database queries
├── core/             # Config, auth, database
└── tests/
```

## Running

```bash
cd api && .venv/bin/python -m uvicorn main:app --reload --port 8000
```

URLs: `/docs` (Swagger), `/health`, `/ready`

## Adding an Endpoint

1. Add route in `routes/`
2. Add schemas in `schemas.py`
3. Add business logic in `services/`
4. Register router in `main.py` if new file
5. Add tests in `tests/`

## Patterns

```python
# Route with auth
from core.auth import UserId
from core.database import DbSession

@router.get("/endpoint")
async def endpoint(user_id: UserId, db: DbSession):
    pass

# Database query
result = await db.execute(select(Model).where(Model.id == id))
item = result.scalar_one_or_none()
```

## Commands

```bash
uv sync                    # Install deps
uv add <pkg>               # Add package
.venv/bin/python -m pytest -v  # Run tests
```
