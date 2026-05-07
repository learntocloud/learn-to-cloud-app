---
name: validate
description: Run ruff lint, ruff format, ty type-check, shared/API tests, start the API, smoke test endpoints, then kill the API. Use after editing Python files to catch errors before commit.
---

# Validate Python Changes

Run linting, formatting, type checking, shared/API tests, start the API, smoke test endpoints, then **clean up**.

**All steps are mandatory. Do not skip API startup and smoke tests.**

Skipping API startup means import errors, circular imports, and route registration bugs won't be caught until production.

---

## When to Use

- After editing Python files
- User says "validate changes", "check my changes", "run checks"
- User says "test the api" or "start the api"
- End of a review workflow

---

## Step 0: Kill Any Existing API Processes

**Always start fresh.**

```bash
lsof -ti:8000 | xargs kill -9 2>/dev/null || true
```

---

## Step 1: Run Ruff Lint

```bash
cd <workspace>/api && uv run ruff check . ../packages/learn-to-cloud-shared
cd <workspace>/apps/verification-functions && uv run ruff check .
```

**If errors found:** Show them and offer to auto-fix with `uv run ruff check --fix <file>`

---

## Step 2: Run Ruff Format Check

```bash
cd <workspace>/api && uv run ruff format --check . ../packages/learn-to-cloud-shared
cd <workspace>/apps/verification-functions && uv run ruff format --check .
```

**If formatting needed:** Offer to fix with `uv run ruff format <file>`

---

## Step 3: Run ty Type Check

```bash
cd <workspace>/api && uv run ty check --exclude scripts --exclude tests .
cd <workspace>/packages/learn-to-cloud-shared && uv run ty check --exclude tests .
cd <workspace>/apps/verification-functions && uv run ty check .
```

---

## Step 4: Start API

**This step catches errors that static analysis misses:**
- Circular imports
- Missing dependencies at runtime
- Route registration failures
- Database connection issues

```bash
cd <workspace>/api
uv run python -m uvicorn learn_to_cloud.main:app --host 127.0.0.1 --port 8000 &
echo $! > .api-pid
sleep 3
```

### Verify Startup

```bash
curl -s --max-time 5 http://localhost:8000/health
```

**Expected**: `{"status":"healthy",...}`

If health check fails, check terminal output for startup errors.

---

## Step 5: Smoke Test Endpoints

```bash
curl -s http://localhost:8000/health
curl -s http://localhost:8000/ready
curl -s http://localhost:8000/openapi.json | head -c 200
```

### Expected Results

| Endpoint | Expected |
|----------|----------|
| `/health` | `{"status":"healthy",...}` |
| `/ready` | `{"status":"ready",...}` (200) or 503 if starting |
| `/openapi.json` | Valid JSON starting with `{"openapi":"3.1.0"...` |

**Why `/openapi.json` is critical**: It forces FastAPI to introspect ALL routes and schemas, catching import errors and schema validation issues.

---

## Step 6: Kill API (Cleanup)

**Always kill the API at the end of validation.**

```bash
if [ -f <workspace>/api/.api-pid ]; then
    kill $(cat <workspace>/api/.api-pid) 2>/dev/null
    rm <workspace>/api/.api-pid
fi
lsof -ti:8000 | xargs kill -9 2>/dev/null || true
```

---

## Step 7: Run Tests

If the changes affect logic (not just formatting/docs), run the test suite:

```bash
cd <workspace>/api && uv run pytest tests/ ../packages/learn-to-cloud-shared/tests -x
cd <workspace>/apps/verification-functions && uv run python -c "import function_app"
```

**Flags:**
- `-x` — stop on first failure for fast feedback

**When mandatory**: Changes to repositories, services, routes, models, schemas, shared verification, or Functions code.

---

## Quick Reference

| Task | Command |
|------|---------|
| Kill API | `lsof -ti:8000 \| xargs kill -9 2>/dev/null \|\| true` |
| Lint | `cd api && uv run ruff check . ../packages/learn-to-cloud-shared && cd ../apps/verification-functions && uv run ruff check .` |
| Lint + fix | `uv run ruff check --fix <file>` |
| Format check | `cd api && uv run ruff format --check . ../packages/learn-to-cloud-shared && cd ../apps/verification-functions && uv run ruff format --check .` |
| Format fix | `uv run ruff format <file>` |
| Type check | `cd api && uv run ty check --exclude scripts --exclude tests . && cd ../packages/learn-to-cloud-shared && uv run ty check --exclude tests . && cd ../../apps/verification-functions && uv run ty check .` |
| Health check | `curl -s http://localhost:8000/health` |

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
| /ready | ✅ 200 | ready |
| /openapi.json | ✅ 200 | Valid JSON |

### 6. Cleanup
✅ API process killed

### 7. Run Tests (Optional)
✅ All passed / ❌ X failures (list them)
```

---

## Common Issues

### Port 8000 already in use

**Cause**: Previous API process wasn't cleaned up.

**Solution**: Run Step 0 cleanup, or: `lsof -ti:8000 | xargs kill -9`

---

## Trigger Phrases

- "validate changes"
- "run ruff and ty"
- "check this file"
- "lint and type check"
- "test the api"
- "start the api"
- "verify my changes"
