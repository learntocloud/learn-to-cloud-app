# Database Strategy

This document outlines the database connection architecture, dependency injection patterns, and lifecycle management used in the Learn to Cloud API.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                     FastAPI Application                         │
├─────────────────────────────────────────────────────────────────┤
│  Lifespan (startup/shutdown)                                    │
│    ├─ create_engine()      → app.state.engine                  │
│    ├─ create_session_maker() → app.state.session_maker         │
│    ├─ init_db()            → verify connectivity               │
│    └─ dispose_engine()     → cleanup on shutdown               │
├─────────────────────────────────────────────────────────────────┤
│  Request Handling                                               │
│    └─ get_db(request) → yields AsyncSession from app.state    │
├─────────────────────────────────────────────────────────────────┤
│  Health Checks                                                  │
│    ├─ check_db_connection(engine)                              │
│    ├─ get_pool_status(engine)                                  │
│    └─ comprehensive_health_check(engine)                       │
└─────────────────────────────────────────────────────────────────┘
```

## State Management Pattern

### FastAPI app.state (Primary)

The engine and session maker are stored in `app.state` and managed by the lifespan context manager:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: create database resources
    app.state.engine = create_engine()
    app.state.session_maker = create_session_maker(app.state.engine)

    yield  # Application runs here

    # Shutdown: cleanup resources
    await dispose_engine(app.state.engine)
```

**Benefits:**
- Explicit lifecycle management
- Guaranteed cleanup on shutdown
- Each test app instance is isolated
- No global state pollution

### Module-Level State (Minimal)

Only the Azure credential is cached at module level:

```python
_azure_credential = None  # Cached DefaultAzureCredential instance
```

**Why kept at module level:**
- Credential object is expensive to create
- Internally caches tokens (~1 hour expiry)
- Stateless caching (doesn't hold connection state)
- Can be reset via `reset_azure_credential()` for testing

## Dependency Injection

### Database Session (`DbSession`)

Routes receive database sessions via FastAPI's dependency injection:

```python
from core.database import DbSession

@router.get("/users/{user_id}")
async def get_user(user_id: str, db: DbSession):
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()
```

**Implementation:**

```python
async def get_db(request: Request) -> AsyncGenerator[AsyncSession]:
    session_maker = request.app.state.session_maker
    async with session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise

DbSession = Annotated[AsyncSession, Depends(get_db)]
```

**Transaction Lifecycle:**
1. Session created from pool
2. Route handler executes queries
3. On success: auto-commit
4. On exception: auto-rollback
5. Session returned to pool

## Connection Pooling

### PostgreSQL (Production)

Uses SQLAlchemy's `AsyncAdaptedQueuePool` with these settings:

| Parameter | Default | Purpose |
|-----------|---------|---------|
| `pool_size` | 5 | Persistent connections |
| `max_overflow` | 10 | Additional connections under load |
| `pool_timeout` | 30s | Wait time for available connection |
| `pool_recycle` | 1800s | Max connection age (30 min) |
| `pool_pre_ping` | True | Test connections before use |

### Pool Monitoring

Pool status is exposed via the `/health/detailed` endpoint:

```json
{
  "pool": {
    "pool_size": 5,
    "checked_out": 1,
    "overflow": 0,
    "checked_in": 4
  }
}
```

Event listeners log warnings when overflow connections are used:

```
WARNING: Pool using overflow connections: 6/5 (+1 overflow)
```

## Azure PostgreSQL Authentication

### Managed Identity Flow

```
┌─────────────┐     ┌──────────────────┐     ┌─────────────────┐
│ App Request │────▶│ DefaultAzure     │────▶│ Azure IMDS      │
│             │     │ Credential       │     │ (Metadata Svc)  │
└─────────────┘     └──────────────────┘     └─────────────────┘
                              │
                              ▼
                    ┌──────────────────┐
                    │ AAD Token        │
                    │ (~1 hour expiry) │
                    └──────────────────┘
                              │
                              ▼
                    ┌──────────────────┐
                    │ asyncpg.connect  │
                    │ (token as pwd)   │
                    └──────────────────┘
```

### Token Acquisition

Tokens are fetched dynamically per new connection via `async_creator`:

```python
async def _azure_asyncpg_creator():
    token = await _get_azure_token()  # With retry + timeout
    return await asyncpg.connect(
        user=settings.postgres_user,
        password=token,  # Token used as password
        host=settings.postgres_host,
        ssl="require",
        ...
    )
```

**Why per-connection:**
- AAD tokens expire (~1 hour)
- Pool reuses connections for longer
- Fresh token on each new connection ensures auth doesn't expire mid-pool

### Retry Logic

Token acquisition includes retry with exponential backoff:

| Parameter | Value | Purpose |
|-----------|-------|---------|
| `stop_after_attempt` | 3 | Max retry attempts |
| `wait_exponential` | 1-10s | Backoff between retries |
| `retry_if_exception_type` | `TimeoutError`, `OSError` | Only transient failures |
| `reraise` | True | Propagate final exception |

**Timeout handling:**
- 30 second timeout per token acquisition attempt
- Credential reset on timeout (in case of bad state)
- Total worst case: 3 attempts × 30s = 90s before failure

## SQLAlchemy Configuration

### Engine Creation

```python
engine = create_async_engine(
    database_url,
    echo=False,              # SQL logging (verbose)
    pool_pre_ping=True,      # Detect stale connections
    pool_size=5,
    max_overflow=10,
    pool_timeout=30,
    pool_recycle=1800,
)
```

### Session Factory

```python
async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,  # Critical for async!
    autocommit=False,
    autoflush=False,
)
```

**Why `expire_on_commit=False`:**
- Default `True` causes implicit lazy loads after commit
- Lazy loading isn't supported in async SQLAlchemy
- Would raise `MissingGreenlet` errors

## Health Checks

### Endpoints

| Endpoint | Purpose | Returns |
|----------|---------|---------|
| `/health` | Basic liveness | Always 200 |
| `/health/detailed` | Component status | DB, Azure auth, pool metrics |
| `/ready` | Readiness probe | 200 only when fully initialized |

### Detailed Health Check Flow

```python
async def comprehensive_health_check(engine):
    # 1. Check Azure auth (if applicable)
    if using_azure:
        await check_azure_token_acquisition()

    # 2. Check database connectivity
    await check_db_connection(engine)

    # 3. Get pool status
    pool_status = get_pool_status(engine)

    return {
        "database": True,
        "azure_auth": True,  # or None if not using Azure
        "pool": pool_status,
    }
```

## File Structure

```
api/
├── core/
│   ├── database.py      # Engine, session, dependencies, health checks
│   └── config.py        # Settings including DB configuration
├── main.py              # Lifespan, app.state management
├── models.py            # SQLAlchemy models (imports Base)
└── alembic/
    └── env.py           # Migrations (separate sync connection)
```

## Alembic Migrations

Alembic uses a **separate synchronous connection** via `psycopg2`:

```python
# alembic/env.py
def _get_sync_database_url():
    if settings.use_azure_postgres:
        token = _get_azure_token_with_retry()  # Sync version
        return f"postgresql+psycopg2://...:{token}@..."
    return settings.database_url.replace("+asyncpg", "+psycopg2")
```

**Why separate connection:**
- Alembic runs in `asyncio.to_thread()` (no event loop)
- DDL operations work better with sync driver
- Avoids sharing async engine state

**Current approach:** Migrations run at app startup via `RUN_MIGRATIONS_ON_STARTUP=true`

**TODO:** Move to CI/CD pipeline for production:
- Pro: Runs once before deploy, not on every restart
- Pro: Faster cold starts
- Con: Requires separate migration job in deployment

## Testing

### Test Fixtures

```python
@pytest.fixture
async def app():
    """Create test app with isolated database state."""
    async with lifespan(test_app):
        yield test_app
    # Cleanup automatic via lifespan

@pytest.fixture
def reset_auth():
    """Reset Azure credential for auth testing."""
    reset_azure_credential()
    yield
    reset_azure_credential()
```

### No Global State Reset Needed

With `app.state` pattern, each test app instance is isolated:
- No need for `reset_db_state()` between tests
- Engine disposed automatically via lifespan
- Only `reset_azure_credential()` needed for auth-specific tests

## Configuration Reference

Environment variables for database configuration:

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | Required | SQLAlchemy connection string |
| `POSTGRES_HOST` | None | If set, enables Azure managed identity auth |
| `POSTGRES_USER` | None | Azure PostgreSQL username (with @host suffix) |
| `POSTGRES_DATABASE` | None | Database name for Azure |
| `DB_POOL_SIZE` | 5 | Connection pool size |
| `DB_POOL_MAX_OVERFLOW` | 10 | Max overflow connections |
| `DB_POOL_TIMEOUT` | 30 | Pool checkout timeout (seconds) |
| `DB_POOL_RECYCLE` | 1800 | Connection recycle time (seconds) |
| `DB_STATEMENT_TIMEOUT_MS` | 30000 | Query timeout (milliseconds) |
| `DB_ECHO` | False | Log all SQL queries |
