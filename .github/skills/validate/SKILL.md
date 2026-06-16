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

## Steps 1-3: Run the Static Checks (lint, format, type-check)

Run the lint, format-check, and type-check commands exactly as listed in the
**Quality Gates** section of `.github/copilot-instructions.md`. That file is the
single source of truth for the command list, so it is not repeated here.

**If lint errors are found:** show them and offer to auto-fix with `uv run ruff check --fix <file>`.
**If formatting is needed:** offer to fix with `uv run ruff format <file>`.

Static checks pass before moving on to starting the API.

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
cd <workspace>/api && uv run pytest tests/ -x
cd <workspace>/packages/learn-to-cloud-shared && uv run pytest tests/ -x
cd <workspace>/apps/verification-functions && uv run python -c "import function_app"
```

**Flags:**
- `-x`: stop on first failure for fast feedback

**When mandatory**: Changes to repositories, services, routes, models, schemas, shared verification, or Functions code.

---

## Step 8: Reproduce CI Environment for New CI Steps

**Mandatory when this change adds or modifies a `.github/workflows/deploy.yml` step that runs a Python script or command.**

CI runs scripts with a minimal env (just `DATABASE__URL` is set in the `ci` job). Local dev shells almost always have more env vars set (devcontainer, `.env` files, shell history). Scripts that work locally can blow up in CI because they touch settings/config that demand env vars CI doesn't have.

This step caught a real production failure (issue #469: `validate_content.py` instantiated `WebSettings` which required `OAUTH__CLIENT_ID`/`OAUTH__CLIENT_SECRET`, both unset in CI).

### How to reproduce CI's env

Strip your shell to bare essentials, then re-run the new CI step's command exactly as it appears in the workflow:

```bash
env -i HOME=$HOME PATH=$PATH \
    DATABASE__URL="postgresql+asyncpg://postgres:postgres@db:5432/learntocloud" \
    uv run python <path/to/new_script.py>
```

`env -i` clears all env vars. `HOME` and `PATH` are kept so `uv` and Python work. `DATABASE__URL` matches the value in `deploy.yml`'s `ci` job env block.

If the new CI step uses additional env vars in the workflow, add them here too, only the ones the workflow sets.

### Pass criteria

- Command exits 0
- Output matches what you expect CI to print
- No `pydantic_core.ValidationError`, `KeyError`, or `EnvironmentError` for missing config

### What to do if it fails

The script depends on something CI doesn't provide. Options in order of preference:

1. **Decouple the script from settings.** The cleanest fix is for scripts to not need full app config (e.g., compute paths from `__file__` instead of reading `Settings.content_dir_path`).
2. **Configure the minimal settings profile inside the script.** Call `configure_settings(WorkerSettings)` or `configure_settings(DatabaseSettings)` at script top before importing modules that touch the settings tree. Suppress `E402` on the late import with `# noqa: E402` and a comment explaining why.
3. **Add the missing env var to the workflow's `env:` block.** Last resort -- expands CI's env surface and risks hiding similar issues in future scripts.

### When to skip this step

Only when the workflow change is purely YAML restructuring with no new Python invocation -- e.g., reordering steps, renaming, changing concurrency keys.

---

## Quick Reference

| Task | Command |
|------|---------|
| Kill API | `lsof -ti:8000 \| xargs kill -9 2>/dev/null \|\| true` |
| Lint / format / type-check | See the **Quality Gates** section of `.github/copilot-instructions.md` (single source of truth) |
| Lint + fix | `uv run ruff check --fix <file>` |
| Format fix | `uv run ruff format <file>` |
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

### 8. CI Env Parity (only if new CI step added)
✅ Passed in stripped env / ❌ Failed -- fix script or workflow / N/A -- no CI step added
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
