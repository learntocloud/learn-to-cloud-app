---
name: validate-changes
description: Run ruff lint, ruff format, ty type-check, start the API, smoke test endpoints, then kill the API. Use after editing Python files to catch errors before commit.
---

# Validate Python Changes

Run linting, formatting, type checking, start the API, smoke test endpoints, then **clean up**.

**⚠️ ALL 7 STEPS ARE MANDATORY. Do not skip Steps 4-6 (API startup, smoke tests, cleanup).**

Skipping API startup means import errors, circular imports, and route registration bugs won't be caught until production.

---

## When to Use

- After editing Python files
- User says "validate changes", "check my changes", "run checks"
- User says "test the api" or "start the api"
- End of a review workflow

---

## Step 0: Kill Any Existing API Processes (REQUIRED)

**Always start fresh** - kill any running uvicorn/API processes:

```bash
pkill -f "uvicorn main:app" || true
```

This ensures port 8000 is free and we're testing fresh code.

---

## Step 1: Run Ruff Lint

Check for linting errors on the specific file(s):

```bash
cd /Users/gps/Developer/learn-to-cloud-app/api
uv run ruff check <file_path>
```

**If errors found:** Show them and offer to auto-fix with `ruff check --fix <file_path>`

---

## Step 2: Run Ruff Format Check

Check formatting without modifying:

```bash
cd /Users/gps/Developer/learn-to-cloud-app/api
uv run ruff format --check <file_path>
```

**If formatting needed:** Offer to fix with `ruff format <file_path>`

---

## Step 3: Run ty Type Check

Run Astral's type checker:

```bash
cd /Users/gps/Developer/learn-to-cloud-app/api
uv run ty check <file_path>
```

For full project check: `uv run ty check`

---

## Step 4: Start API (REQUIRED - Do Not Skip)

**This step catches errors that static analysis misses:**
- Circular imports
- Missing dependencies at runtime
- Route registration failures
- Database connection issues

```bash
cd /Users/gps/Developer/learn-to-cloud-app/api
uv sync && uv run python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

Run as background process (`isBackground=true`), then:

1. Check terminal output for startup success
2. Verify "Application startup complete" appears
3. If failed, report error and skip endpoint tests

---

## Step 5: Smoke Test Endpoints (REQUIRED - Do Not Skip)

After API starts successfully, test these unauthenticated endpoints:

```bash
# Basic health check
curl -s http://localhost:8000/health

# Detailed health (includes DB status)
curl -s http://localhost:8000/health/detailed

# Readiness check (verifies init completed)
curl -s http://localhost:8000/ready

# OpenAPI schema loads (catches import/schema errors)
curl -s http://localhost:8000/openapi.json | head -c 200
```

**Expected results:**
- `/health` → `{"status":"healthy",...}`
- `/health/detailed` → Shows database: true/false
- `/ready` → 200 if ready, 503 if still starting
- `/openapi.json` → Valid JSON (catches route/schema errors)

**Why these endpoints:**
- No authentication required
- Tests database connectivity
- Catches import errors, schema validation issues, route registration problems
- `/openapi.json` forces FastAPI to introspect ALL routes and schemas

---

## Step 6: Kill API (REQUIRED - Cleanup)

**Always kill the API at the end of validation:**

```bash
pkill -f "uvicorn main:app" || true
```

This prevents:
- Port conflicts on next run
- Stale processes running old code
- Resource leaks

---

## Quick Commands Reference

| Task | Command |
|------|---------|
| Kill API | `pkill -f "uvicorn main:app" \|\| true` |
| Lint file | `uv run ruff check <file>` |
| Lint + fix | `uv run ruff check --fix <file>` |
| Format check | `uv run ruff format --check <file>` |
| Format fix | `uv run ruff format <file>` |
| Type check file | `uv run ty check <file>` |
| Type check all | `uv run ty check` |
| Start API | `uv sync && uv run python -m uvicorn main:app --host 0.0.0.0 --port 8000` |
| Health check | `curl -s http://localhost:8000/health` |
| Detailed health | `curl -s http://localhost:8000/health/detailed` |
| Readiness | `curl -s http://localhost:8000/ready` |
| OpenAPI schema | `curl -s http://localhost:8000/openapi.json \| head -c 200` |

---

## Full Validation Flow

When user says "validate changes" after editing `<file>`:

```markdown
## Validation: <filename>

### 0. Kill Existing API
✅ Cleaned up / ⚠️ No process running

### 1. Ruff Lint
✅ No issues / ❌ X issues found (list them)

### 2. Ruff Format
✅ Formatted correctly / ❌ Needs formatting (offer to fix)

### 3. ty Type Check
✅ No type errors / ❌ X errors (list them)

### 4. API Startup
✅ "Application startup complete" / ❌ Failed to start (show error)

### 5. Endpoint Smoke Tests
| Endpoint | Status | Response |
|----------|--------|----------|
| /health | ✅ 200 | healthy |
| /health/detailed | ✅ 200 | database: true |
| /ready | ✅ 200 | healthy |
| /openapi.json | ✅ 200 | Valid JSON |

### 6. Cleanup
✅ API process killed
```

---

## Example Trigger Phrases

- "validate changes"
- "run ruff and ty"
- "check this file"
- "lint and type check"
- "test the api"
- "start the api"
- "verify my changes"
