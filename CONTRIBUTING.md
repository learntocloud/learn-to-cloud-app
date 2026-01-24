# Contributing to Learn to Cloud App

Thanks for your interest in contributing! This guide covers how to set up your development environment and contribute to the project.

## Prerequisites

| Tool | Version | Installation |
|------|---------|--------------|
| Python | 3.13+ | [python.org](https://www.python.org/downloads/) |
| uv | Latest | [docs.astral.sh/uv](https://docs.astral.sh/uv/) |
| Node.js | 20+ | [nodejs.org](https://nodejs.org/) |
| Docker | Latest | [docker.com](https://www.docker.com/get-started) |

## Getting Started

### 1. Clone the Repository

```bash
git clone https://github.com/learntocloud/learn-to-cloud-app.git
cd learn-to-cloud-app
```

### 2. Start the Database

```bash
docker compose up -d db
```

### 3. Set Up the API

```bash
cd api
uv venv                    # Create virtual environment
uv sync --all-groups       # Install all dependencies (including dev)
cp .env.example .env       # Create environment config
```

Run migrations:

```bash
uv run alembic upgrade head
```

Start the API:

```bash
uv run uvicorn main:app --reload --port 8000
```

### 4. Set Up the Frontend

```bash
cd frontend
npm install
cp .env.example .env.local  # Add VITE_CLERK_PUBLISHABLE_KEY
npm run dev
```

### 5. Install Pre-commit Hooks

Pre-commit hooks run automatically on `git commit` to catch issues early:

```bash
# Install pre-commit (if not already installed)
pip install pre-commit
# or: uv tool install pre-commit

# Install the hooks
pre-commit install
```

## Development Workflow

### Running Tests

**API (Python):**

```bash
cd api
uv run pytest tests/ -v              # Run all tests
uv run pytest tests/ -v -m unit      # Run only unit tests
uv run pytest tests/ -v -m integration  # Run only integration tests
uv run pytest tests/ --cov           # Run with coverage
```

**Frontend (TypeScript):**

```bash
cd frontend
npm test                    # Run tests in watch mode
npm test -- --run           # Run tests once
npm run test:coverage       # Run with coverage
```

### Linting & Formatting

**API:**

```bash
cd api
uv run ruff check .         # Lint
uv run ruff check . --fix   # Lint and auto-fix
uv run ruff format .        # Format
uv run ty check             # Type check
```

**Frontend:**

```bash
cd frontend
npm run lint                # ESLint
npx tsc --noEmit            # TypeScript check
```

### Pre-commit (All Checks)

Run all checks manually without committing:

```bash
uvx pre-commit run --all-files
```

This runs:
- Trailing whitespace & end-of-file fixes
- YAML/JSON validation
- Ruff lint & format (Python)
- ty type check (Python)
- pytest (Python)
- ESLint (TypeScript)
- TypeScript check
- Vitest (TypeScript)

## Code Style

### Python (API)

- **Formatter:** Ruff (88 char line length)
- **Linter:** Ruff (E, F, I, UP rules)
- **Type Checker:** ty
- Follow existing patterns in `services/`, `routes/`, `repositories/`

### TypeScript (Frontend)

- **Formatter:** Prettier (via ESLint)
- **Linter:** ESLint with TypeScript plugin
- Use functional components with hooks
- Follow existing patterns in `components/`, `pages/`, `lib/`

## Project Structure

```
api/
├── main.py              # FastAPI app entry point
├── models.py            # SQLAlchemy models
├── schemas.py           # Pydantic request/response schemas
├── routes/              # API endpoint handlers
├── services/            # Business logic
├── repositories/        # Database queries (async SQLAlchemy)
├── core/                # Config, auth, database, logging
└── tests/               # pytest tests (unit & integration)

frontend/
└── src/
    ├── components/      # Reusable React components
    ├── pages/           # Page components (routes)
    ├── lib/             # API client, hooks, utilities
    └── mocks/           # MSW handlers for testing
```

## Writing Tests

### Python Test Conventions

```python
"""Tests for feature_service."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from services.feature_service import do_something
from tests.factories import UserFactory, create_async

# Place pytestmark AFTER all imports
pytestmark = pytest.mark.integration  # or pytest.mark.unit


class TestDoSomething:
    """Tests for do_something()."""

    async def test_does_the_thing(self, db_session: AsyncSession):
        """Should do the expected thing."""
        user = await create_async(UserFactory, db_session)
        result = await do_something(db_session, user.id)
        assert result.success is True
```

### TypeScript Test Conventions

```typescript
import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { MyComponent } from './MyComponent';

describe('MyComponent', () => {
  it('renders correctly', () => {
    render(<MyComponent />);
    expect(screen.getByText('Hello')).toBeInTheDocument();
  });
});
```

## Commit Messages

Use clear, descriptive commit messages:

```
feat: add certificate PDF download
fix: correct streak calculation for timezone edge case
docs: update API documentation
test: add integration tests for webhooks
refactor: extract badge computation to service
```

## Pull Requests

1. Create a feature branch from `main`
2. Make your changes
3. Ensure all pre-commit hooks pass
4. Push and open a PR
5. Fill out the PR template
6. Request review

## Getting Help

- Check existing code for patterns
- Read the docs in `/docs`
- Use GitHub Copilot agent skills in `.github/skills/`

## Common Issues

### Pre-commit fails with "command not found"

Make sure `uv` and `npm` are in your PATH:

```bash
# Check uv
uv --version

# Check npm
npm --version
```

### Database connection errors

Ensure Docker is running and the database is up:

```bash
docker compose up -d db
docker compose ps  # Should show db as "running"
```

### TypeScript errors about missing modules

Install frontend dependencies:

```bash
cd frontend
npm install
```
