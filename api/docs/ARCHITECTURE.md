# Learn to Cloud API - Architecture Documentation

## Table of Contents
1. [Overview](#overview)
2. [Layered Architecture](#layered-architecture)
3. [Layer Responsibilities](#layer-responsibilities)
4. [Data Flow](#data-flow)
5. [Import Rules](#import-rules)
6. [DTO Pattern](#dto-pattern)
7. [Code Review Checklist](#code-review-checklist)
8. [Examples](#examples)

---

## Overview

The Learn to Cloud API follows a **strict layered architecture** with clear separation of concerns. Each layer has a single, well-defined responsibility, and dependencies flow in one direction only.

### Architecture Diagram

```
┌─────────────────────────────────────────────────────┐
│                    HTTP Request                      │
└──────────────────┬──────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────┐
│              ROUTES (HTTP Layer)                     │
│  - HTTP concerns only (status codes, headers)       │
│  - Request validation                                │
│  - DTO → Pydantic Schema conversion                  │
│  - Delegates all logic to services                   │
└──────────────────┬──────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────┐
│             SERVICES (Business Logic)                │
│  - Business rules and validation                     │
│  - Orchestration and coordination                    │
│  - ORM Model → DTO conversion                        │
│  - Returns DTOs (dataclasses)                        │
└──────────────────┬──────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────┐
│           REPOSITORIES (Data Access)                 │
│  - Database queries (CRUD operations)                │
│  - No business logic or transformations              │
│  - Returns ORM models or primitives                  │
└──────────────────┬──────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────┐
│              MODELS (ORM Definitions)                │
│  - SQLAlchemy model definitions                      │
│  - Relationships and constraints                     │
│  - No methods (except properties)                    │
└─────────────────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────┐
│                   DATABASE                           │
└─────────────────────────────────────────────────────┘
```

---

## Layered Architecture

### Layer 1: Models (ORM)
- **Location:** `models.py`
- **Purpose:** SQLAlchemy ORM model definitions
- **Responsibility:** Define database schema as Python classes

### Layer 2: Schemas (API I/O)
- **Location:** `schemas.py`
- **Purpose:** Pydantic models for request/response validation
- **Responsibility:** Input validation and API contract definition

### Layer 3: Repositories (Data Access)
- **Location:** `repositories/`
- **Purpose:** Abstract database operations
- **Responsibility:** CRUD operations and database queries

### Layer 4: Services (Business Logic)
- **Location:** `services/`
- **Purpose:** Business logic implementation
- **Responsibility:** Application logic, orchestration, validation

### Layer 5: Routes (HTTP Handlers)
- **Location:** `routes/`
- **Purpose:** HTTP endpoint handlers
- **Responsibility:** HTTP request/response handling

### Supporting Layers

#### Core (Infrastructure)
- **Location:** `core/`
- **Purpose:** Application infrastructure
- **Modules:**
  - `auth.py` - Authentication/authorization
  - `config.py` - Configuration management
  - `database.py` - Database connection and session management
  - `telemetry.py` - Observability and monitoring
  - `ratelimit.py` - Rate limiting middleware

#### Migrations (Schema Evolution)
- **Location:** `alembic/`
- **Purpose:** Database schema version control
- **Responsibility:** Schema changes only, no business logic

---

## Layer Responsibilities

### ✅ Models Layer: What's Allowed

**ALLOWED:**
- SQLAlchemy column definitions (`mapped_column`, `Mapped`)
- Relationships (`relationship`, `ForeignKey`)
- Table constraints (`UniqueConstraint`, `Index`)
- Simple `@property` for computed attributes
- Enums for fixed value sets

**FORBIDDEN:**
- Business logic methods
- Data validation (use schemas)
- Query methods (use repositories)
- String parsing or transformations
- HTTP concerns

**Example:**
```python
class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True)
    github_username: Mapped[str | None] = mapped_column(String(255))

    # ✅ Relationship definition is OK
    submissions: Mapped[list["Submission"]] = relationship(
        "Submission", back_populates="user", cascade="all, delete-orphan"
    )
```

---

### ✅ Schemas Layer: What's Allowed

**ALLOWED:**
- Pydantic model definitions
- Field validators (`@field_validator`)
- Format validation (regex, length, type)
- Computed fields (`@computed_field`)

**FORBIDDEN:**
- Business logic (calculations, decisions)
- Database operations
- Service layer imports
- ORM model imports (except for type hints)

**Example:**
```python
class QuestionSubmitRequest(BaseModel):
    topic_id: str
    question_id: str
    user_answer: str

    @field_validator("topic_id")
    @classmethod
    def validate_topic_id(cls, v: str) -> str:
        # ✅ Format validation is OK
        if not v.startswith("phase"):
            raise ValueError("topic_id must start with 'phase'")
        return v

    @field_validator("user_answer")
    @classmethod
    def validate_answer_not_empty(cls, v: str) -> str:
        # ✅ Length validation is OK
        if not v.strip():
            raise ValueError("Answer cannot be empty")
        return v
```

---

### ✅ Repositories Layer: What's Allowed

**ALLOWED:**
- Database queries (SELECT, INSERT, UPDATE, DELETE)
- SQLAlchemy query construction
- Transaction management (`flush()`, `commit()`)
- Return ORM models or primitive types
- Database utility functions (`upsert_on_conflict` in `repositories/utils.py`)

**FORBIDDEN:**
- Business logic (calculations, rules, decisions)
- String parsing (e.g., extracting phase ID from topic_id)
- Data transformation (e.g., `.lower()` normalization)
- Service layer imports
- HTTP concerns

**Example:**
```python
class UserRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, user_id: str) -> User | None:
        # ✅ Pure database query
        result = await self.db.execute(
            select(User).where(User.id == user_id)
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        user_id: str,
        email: str,
        github_username: str | None = None,
    ) -> User:
        # ✅ Simple CRUD operation
        # ✅ Expects pre-normalized data from service
        user = User(
            id=user_id,
            email=email,
            github_username=github_username,  # Already normalized
        )
        self.db.add(user)
        await self.db.flush()
        return user
```

**Counter-Example (WRONG):**
```python
class UserRepository:
    async def create(self, github_username: str | None = None) -> User:
        # ❌ Data transformation in repository
        user = User(
            github_username=github_username.lower() if github_username else None
        )
        return user

    def is_placeholder(self, user: User) -> bool:
        # ❌ Business logic in repository
        return user.email.endswith("@placeholder.local")
```

---

### ✅ Services Layer: What's Allowed

**ALLOWED:**
- Business logic (rules, calculations, decisions)
- Orchestration (calling multiple repositories)
- String parsing/transformation
- External API calls
- Return DTOs (dataclasses), never ORM models
- Import from other services
- Import from repositories

**FORBIDDEN:**
- Direct database queries (use repositories)
- Return ORM models (convert to DTOs)
- HTTP status codes or response building (use routes)
- Schema manipulation (routes handle conversion)

**Example:**
```python
@dataclass(frozen=True)
class UserData:
    """DTO for user (service return type)."""
    id: str
    email: str
    github_username: str | None

def _normalize_github_username(username: str | None) -> str | None:
    """Normalize GitHub username to lowercase."""
    # ✅ Data transformation in service layer
    return username.lower() if username else None

def _is_placeholder_user(user_email: str) -> bool:
    """Check if user email indicates placeholder account."""
    # ✅ Business logic in service layer
    return user_email.endswith("@placeholder.local")

async def get_or_create_user(db: AsyncSession, user_id: str) -> UserData:
    # ✅ Service orchestration
    user_repo = UserRepository(db)
    user = await user_repo.get_or_create(user_id)

    # ✅ Business logic check
    if _is_placeholder_user(user.email):
        clerk_data = await fetch_user_data(user_id)
        if clerk_data:
            # ✅ Normalize before passing to repository
            normalized_username = _normalize_github_username(
                clerk_data.github_username
            )
            await user_repo.update(user, github_username=normalized_username)

    # ✅ Convert ORM model to DTO before returning
    return UserData(
        id=user.id,
        email=user.email,
        github_username=user.github_username,
    )
```

---

### ✅ Routes Layer: What's Allowed

**ALLOWED:**
- HTTP request/response handling
- Status codes and headers
- HTTPException usage
- DTO → Pydantic Schema conversion
- Dependency injection (UserId, DbSession)
- Rate limiting decorators

**FORBIDDEN:**
- Business logic
- Direct database access
- Repository imports
- Complex data transformations
- ORM model manipulation

**Example:**
```python
@router.get("/api/user/me")
async def get_current_user(
    user_id: UserId,
    db: DbSession,
) -> UserResponse:
    # ✅ Delegate to service
    user = await get_or_create_user(db, user_id)

    # ✅ Convert DTO to Pydantic schema
    return UserResponse.model_validate(asdict(user))
```

**Counter-Example (WRONG):**
```python
@router.get("/api/user/me")
async def get_current_user(user_id: UserId, db: DbSession) -> UserResponse:
    # ❌ Direct repository usage in route
    user_repo = UserRepository(db)
    user = await user_repo.get_by_id(user_id)

    # ❌ Business logic in route
    if user.email.endswith("@placeholder.local"):
        # Do something...
        pass

    return UserResponse.model_validate(asdict(user))
```

---

## Data Flow

### Request Flow (Client → Database)

```
1. HTTP Request arrives at Route
   ↓
2. Route validates request (Pydantic schema)
   ↓
3. Route calls Service with validated data
   ↓
4. Service executes business logic
   ↓
5. Service calls Repository for data access
   ↓
6. Repository executes database query
   ↓
7. Repository returns ORM model to Service
```

### Response Flow (Database → Client)

```
1. Service receives ORM model from Repository
   ↓
2. Service converts ORM model → DTO (dataclass)
   ↓
3. Service returns DTO to Route
   ↓
4. Route converts DTO → Pydantic Schema
   ↓
5. FastAPI serializes Schema → JSON
   ↓
6. HTTP Response sent to client
```

### Data Transformation Boundaries

```
Database Row
    ↓
ORM Model (models.User)
    ↓ [Repository returns]
ORM Model (in service)
    ↓ [Service converts]
DTO (UserData dataclass)
    ↓ [Service returns]
DTO (in route)
    ↓ [Route converts]
Pydantic Schema (UserResponse)
    ↓ [FastAPI serializes]
JSON Response
```

**Key Points:**
- ORM models NEVER escape repositories
- Services ALWAYS return DTOs
- Routes ALWAYS convert DTOs to Pydantic schemas

---

## Import Rules

### Allowed Import Dependencies

```
Routes → Services → Repositories → Models
  ↓         ↓            ↓
Schemas   Schemas      Models
```

### Import Matrix

| From ↓ To → | Models | Schemas | Repositories | Services | Routes | Core |
|-------------|--------|---------|--------------|----------|--------|------|
| **Routes** | ❌ | ✅ | ❌ | ✅ | ✅ | ✅ |
| **Services** | ✅ | ✅ | ✅ | ✅ | ❌ | ✅ |
| **Repositories** | ✅ | ❌ | ✅* | ❌ | ❌ | ✅ |
| **Schemas** | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ |
| **Models** | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |

*Repositories can import from `repositories/utils.py` for shared utilities

### Verification Commands

```bash
# Routes should NOT import from repositories
grep -r "^from repositories" routes/
# Should return nothing

# Routes should NOT import from models
grep -r "^from models import" routes/
# Should return nothing

# Services should NOT use raw SQL
grep -r "from sqlalchemy import.*text" services/
# Should return nothing (or minimal)

# Repositories should NOT have string manipulation
grep -rE "\.split\(|\.replace\(|\.lower\(" repositories/
# Should return nothing
```

---

## DTO Pattern

### Why DTOs?

DTOs (Data Transfer Objects) prevent **ORM leakage** - the anti-pattern where ORM models escape the repository layer and spread throughout the application.

### DTO Benefits

1. **Explicit contracts** - Services define what data they return
2. **Immutability** - DTOs are frozen, preventing accidental mutation
3. **Decoupling** - Changes to database schema don't break services/routes
4. **Type safety** - Clear data structures with type hints

### DTO Definition Pattern

```python
from dataclasses import dataclass
from datetime import datetime

@dataclass(frozen=True)
class UserData:
    """DTO for user information (service layer return type)."""
    id: str
    email: str
    first_name: str | None
    last_name: str | None
    github_username: str | None
    is_admin: bool
    created_at: datetime
```

**Key points:**
- Use `@dataclass(frozen=True)` for immutability
- Clear docstring indicating it's a DTO
- Type hints for all fields
- No methods (pure data)

### ORM → DTO Conversion

```python
def _to_user_data(user: User) -> UserData:
    """Convert ORM model to DTO."""
    return UserData(
        id=user.id,
        email=user.email,
        first_name=user.first_name,
        last_name=user.last_name,
        github_username=user.github_username,
        is_admin=user.is_admin,
        created_at=user.created_at,
    )

async def get_user(db: AsyncSession, user_id: str) -> UserData:
    repo = UserRepository(db)
    user = await repo.get_by_id(user_id)  # ORM model
    return _to_user_data(user)  # Convert to DTO immediately
```

### DTO → Schema Conversion (in Routes)

```python
from dataclasses import asdict

@router.get("/api/user/me")
async def get_current_user(
    user_id: UserId,
    db: DbSession,
) -> UserResponse:
    user_dto = await get_user(db, user_id)  # Returns DTO

    # Convert DTO to Pydantic schema
    return UserResponse.model_validate(asdict(user_dto))
```

---

## Code Review Checklist

### For Pull Requests

#### Models
- [ ] Only contains ORM definitions
- [ ] No business logic methods
- [ ] No validation logic (use schemas)
- [ ] Relationships are properly defined

#### Schemas
- [ ] Only Pydantic models for API I/O
- [ ] Field validators are format/type checks only
- [ ] No business logic
- [ ] No database imports

#### Repositories
- [ ] Only CRUD operations
- [ ] No string parsing (e.g., extracting IDs from formatted strings)
- [ ] No data transformation (e.g., `.lower()` normalization)
- [ ] No business rules or decisions
- [ ] Returns ORM models or primitives

#### Services
- [ ] Returns DTOs (dataclasses), not ORM models
- [ ] Business logic properly encapsulated
- [ ] Uses repositories for all database access
- [ ] No raw SQL queries
- [ ] Proper error handling

#### Routes
- [ ] No business logic
- [ ] Delegates all logic to services
- [ ] Converts DTOs to Pydantic schemas
- [ ] No repository imports
- [ ] Only HTTP concerns (status codes, headers, exceptions)

#### General
- [ ] No circular imports
- [ ] Import dependencies follow the rules
- [ ] Proper error handling at each layer
- [ ] Type hints used throughout

---

## Examples

### Example 1: User Creation Flow

**Route:**
```python
@router.post("/api/users")
async def create_user(
    request: CreateUserRequest,  # Pydantic schema
    db: DbSession,
) -> UserResponse:
    # ✅ Delegate to service
    user = await create_new_user(
        db=db,
        email=request.email,
        github_username=request.github_username,
    )

    # ✅ Convert DTO to schema
    return UserResponse.model_validate(asdict(user))
```

**Service:**
```python
async def create_new_user(
    db: AsyncSession,
    email: str,
    github_username: str | None,
) -> UserData:
    # ✅ Business logic: normalize username
    normalized_username = _normalize_github_username(github_username)

    # ✅ Use repository for database access
    user_repo = UserRepository(db)
    user = await user_repo.create(
        user_id=generate_id(),
        email=email,
        github_username=normalized_username,
    )

    # ✅ Convert ORM to DTO before returning
    return _to_user_data(user)
```

**Repository:**
```python
async def create(
    self,
    user_id: str,
    email: str,
    github_username: str | None = None,
) -> User:
    # ✅ Pure database operation
    # ✅ Expects pre-normalized data
    user = User(
        id=user_id,
        email=email,
        github_username=github_username,
    )
    self.db.add(user)
    await self.db.flush()
    return user
```

---

### Example 2: Phase Completion Check

**Route:**
```python
@router.get("/api/phases/{phase_id}/progress")
async def get_phase_progress(
    phase_id: int,
    user_id: UserId,
    db: DbSession,
) -> PhaseProgressResponse:
    # ✅ Delegate to service
    progress = await fetch_user_progress(db, user_id)
    phase_progress = progress.phases.get(phase_id)

    if not phase_progress:
        raise HTTPException(status_code=404, detail="Phase not found")

    # ✅ Convert DTO to schema
    return PhaseProgressResponse(
        phase_id=phase_progress.phase_id,
        is_complete=phase_progress.is_complete,  # ✅ Use DTO property
        percentage=phase_progress.overall_percentage,
    )
```

**Service:**
```python
@dataclass
class PhaseProgress:
    phase_id: int
    steps_completed: int
    steps_required: int
    questions_passed: int
    questions_required: int
    hands_on_validated: bool

    @property
    def is_complete(self) -> bool:
        """Phase is complete when all requirements are met."""
        # ✅ Business logic in service layer
        return (
            self.steps_completed >= self.steps_required
            and self.questions_passed >= self.questions_required
            and self.hands_on_validated
        )

async def fetch_user_progress(
    db: AsyncSession,
    user_id: str,
) -> UserProgress:
    # ✅ Get raw data from repositories
    question_repo = QuestionAttemptRepository(db)
    step_repo = StepProgressRepository(db)

    question_ids = await question_repo.get_all_passed_question_ids(user_id)
    topic_ids = await step_repo.get_completed_step_topic_ids(user_id)

    # ✅ Business logic: parse phase numbers from IDs
    phase_questions = {}
    for question_id in question_ids:
        phase_num = _parse_phase_from_question_id(question_id)
        if phase_num:
            phase_questions[phase_num] = phase_questions.get(phase_num, 0) + 1

    # ✅ Return DTO with computed data
    return UserProgress(user_id=user_id, phases=phases)
```

**Repository:**
```python
async def get_all_passed_question_ids(self, user_id: str) -> list[str]:
    # ✅ Pure database query, returns raw IDs
    result = await self.db.execute(
        select(func.distinct(QuestionAttempt.question_id)).where(
            QuestionAttempt.user_id == user_id,
            QuestionAttempt.is_passed.is_(True),
        )
    )
    return [row[0] for row in result.all()]
```

**Service Helper:**
```python
def _parse_phase_from_question_id(question_id: str) -> int | None:
    """Extract phase number from question_id (phase{N}-topic{M}-q{X})."""
    # ✅ String parsing in service layer (NOT repository)
    if not question_id.startswith("phase"):
        return None
    try:
        return int(question_id.split("-")[0].replace("phase", ""))
    except (ValueError, IndexError):
        return None
```

---

## Common Anti-Patterns to Avoid

### ❌ Anti-Pattern 1: ORM Leakage

**Wrong:**
```python
# Service returns ORM model
async def get_user(db: AsyncSession, user_id: str) -> User:  # ❌
    repo = UserRepository(db)
    return await repo.get_by_id(user_id)  # Returns ORM model
```

**Correct:**
```python
# Service returns DTO
async def get_user(db: AsyncSession, user_id: str) -> UserData:  # ✅
    repo = UserRepository(db)
    user = await repo.get_by_id(user_id)
    return _to_user_data(user)  # Convert to DTO
```

---

### ❌ Anti-Pattern 2: Business Logic in Repository

**Wrong:**
```python
class UserRepository:
    async def count_by_phase(self, user_id: str) -> dict[int, int]:
        result = await self.db.execute(...)
        phase_counts = {}
        for topic_id in result:
            # ❌ String parsing in repository
            phase_num = int(topic_id.split("-")[0].replace("phase", ""))
            phase_counts[phase_num] = phase_counts.get(phase_num, 0) + 1
        return phase_counts
```

**Correct:**
```python
class UserRepository:
    async def get_completed_topic_ids(self, user_id: str) -> list[str]:
        # ✅ Returns raw data
        result = await self.db.execute(...)
        return [row[0] for row in result.all()]

# In service:
def _parse_phase_from_topic_id(topic_id: str) -> int | None:
    # ✅ Parsing in service layer
    if not topic_id.startswith("phase"):
        return None
    try:
        return int(topic_id.split("-")[0].replace("phase", ""))
    except (ValueError, IndexError):
        return None
```

---

### ❌ Anti-Pattern 3: Business Logic in Routes

**Wrong:**
```python
@router.get("/api/user/dashboard")
async def get_dashboard(user_id: UserId, db: DbSession):
    repo = UserRepository(db)
    user = await repo.get_by_id(user_id)

    # ❌ Business logic in route
    if user.email.endswith("@placeholder.local"):
        user_data = await sync_from_clerk(user_id)
        await repo.update(user, **user_data)

    return DashboardResponse(...)
```

**Correct:**
```python
@router.get("/api/user/dashboard")
async def get_dashboard(user_id: UserId, db: DbSession):
    # ✅ Delegate to service
    dashboard = await get_dashboard_data(db, user_id)

    # ✅ Simple DTO → Schema conversion
    return DashboardResponse.model_validate(asdict(dashboard))

# In service:
async def get_dashboard_data(db: AsyncSession, user_id: str) -> DashboardData:
    # ✅ Business logic in service
    user = await get_or_create_user(db, user_id)
    # ... rest of logic
```

---

## Additional Resources

- [FastAPI Best Practices](https://fastapi.tiangolo.com/tutorial/)
- [SQLAlchemy ORM Documentation](https://docs.sqlalchemy.org/en/20/orm/)
- [Pydantic Documentation](https://docs.pydantic.dev/)
- [Clean Architecture](https://blog.cleancoder.com/uncle-bob/2012/08/13/the-clean-architecture.html)

---

## Questions?

For architecture questions or clarifications, please:
1. Review this document
2. Check existing code for patterns
3. Ask in team discussion channels
