---
name: validate-changes
description: Run ruff lint, ruff format, ty type-check, start the API, smoke test endpoints, then kill the API. Use after editing Python files to catch errors before commit.
---

# Validate Python Changes

Run linting, formatting, type checking, start the API, smoke test endpoints, then **clean up**.

**⚠️ ALL STEPS ARE MANDATORY. Do not skip API startup and smoke tests.**

Skipping API startup means import errors, circular imports, and route registration bugs won't be caught until production.

---

## When to Use

- After editing Python files
- User says "validate changes", "check my changes", "run checks"
- User says "test the api" or "start the api"
- End of a review workflow

---

## Platform Detection

**CRITICAL**: Detect the OS first and use appropriate commands:

- **Windows**: Use PowerShell commands (`Invoke-WebRequest`, `Stop-Process`, etc.)
- **macOS/Linux**: Use bash commands (`curl`, `pkill`, etc.)

---

## Step 0: Kill Any Existing API Processes

**Always start fresh** - kill any running uvicorn/API processes.

### Windows (PowerShell)
```powershell
Get-Process -Name "python" -ErrorAction SilentlyContinue | ForEach-Object {
    $cmd = (Get-CimInstance Win32_Process -Filter "ProcessId = $($_.Id)" -ErrorAction SilentlyContinue).CommandLine
    if ($cmd -like "*uvicorn*main:app*") { Stop-Process -Id $_.Id -Force }
}
```

### macOS/Linux
```bash
pkill -f "uvicorn main:app" || true
```

---

## Step 1: Run Ruff Lint

**IMPORTANT**: Always `cd` to the api directory first.

### Windows (PowerShell)
```powershell
Set-Location <workspace>\api; uv run ruff check <relative_file_path>
```

### macOS/Linux
```bash
cd <workspace>/api && uv run ruff check <relative_file_path>
```

**If errors found:** Show them and offer to auto-fix with `uv run ruff check --fix <file>`

---

## Step 2: Run Ruff Format Check

### Windows (PowerShell)
```powershell
Set-Location <workspace>\api; uv run ruff format --check <relative_file_path>
```

### macOS/Linux
```bash
cd <workspace>/api && uv run ruff format --check <relative_file_path>
```

**If formatting needed:** Offer to fix with `uv run ruff format <file>`

---

## Step 3: Run ty Type Check

### Windows (PowerShell)
```powershell
Set-Location <workspace>\api; uv run ty check <relative_file_path>
```

### macOS/Linux
```bash
cd <workspace>/api && uv run ty check <relative_file_path>
```

---

## Step 4: Start API (CRITICAL)

**This step catches errors that static analysis misses:**
- Circular imports
- Missing dependencies at runtime
- Route registration failures
- Database connection issues

### Windows - Use Start-Process for Persistence

**⚠️ CRITICAL**: On Windows, background terminal commands get killed when new commands run. You MUST use `Start-Process` to spawn a separate PowerShell window:

```powershell
# Start API in a separate persistent process
$proc = Start-Process -FilePath "powershell" -ArgumentList @(
    "-NoExit", "-Command",
    "Set-Location '<workspace>\api'; .\.venv\Scripts\Activate.ps1; python -m uvicorn main:app --port 8000"
) -PassThru

# Save PID for cleanup
$proc.Id | Out-File "<workspace>\api\.api-pid"

# Wait for startup
Start-Sleep -Seconds 4
```

### macOS/Linux
```bash
cd <workspace>/api
uv run python -m uvicorn main:app --host 0.0.0.0 --port 8000 &
echo $! > .api-pid
sleep 3
```

### Verify Startup

After starting, **check that API is responding** before proceeding:

#### Windows
```powershell
(Invoke-WebRequest -Uri "http://localhost:8000/health" -UseBasicParsing -TimeoutSec 5).Content
```

#### macOS/Linux
```bash
curl -s --max-time 5 http://localhost:8000/health
```

**Expected**: `{"status":"healthy",...}`

If health check fails, check terminal output for startup errors.

---

## Step 5: Smoke Test Endpoints

Test these unauthenticated endpoints to catch runtime issues:

### Windows (PowerShell)
```powershell
# Health check
(Invoke-WebRequest -Uri "http://localhost:8000/health" -UseBasicParsing).Content

# Detailed health (DB status)
(Invoke-WebRequest -Uri "http://localhost:8000/health/detailed" -UseBasicParsing).Content

# Readiness
(Invoke-WebRequest -Uri "http://localhost:8000/ready" -UseBasicParsing).Content

# OpenAPI schema (validates ALL routes and schemas)
(Invoke-WebRequest -Uri "http://localhost:8000/openapi.json" -UseBasicParsing).Content.Substring(0, 200)
```

### macOS/Linux
```bash
curl -s http://localhost:8000/health
curl -s http://localhost:8000/health/detailed
curl -s http://localhost:8000/ready
curl -s http://localhost:8000/openapi.json | head -c 200
```

### Expected Results

| Endpoint | Expected |
|----------|----------|
| `/health` | `{"status":"healthy",...}` |
| `/health/detailed` | Shows `"database":true` or `false` |
| `/ready` | `{"status":"ready",...}` (200) or 503 if starting |
| `/openapi.json` | Valid JSON starting with `{"openapi":"3.1.0"...` |

**Why `/openapi.json` is critical**: It forces FastAPI to introspect ALL routes and schemas, catching import errors and schema validation issues.

---

## Step 6: Kill API (Cleanup)

**Always kill the API at the end of validation.**

### Windows
```powershell
# Kill by saved PID
$pidFile = "<workspace>\api\.api-pid"
if (Test-Path $pidFile) {
    $pid = Get-Content $pidFile
    Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
    Remove-Item $pidFile
}

# Also kill any stray processes
Get-Process -Name "python" -ErrorAction SilentlyContinue | ForEach-Object {
    $cmd = (Get-CimInstance Win32_Process -Filter "ProcessId = $($_.Id)" -ErrorAction SilentlyContinue).CommandLine
    if ($cmd -like "*uvicorn*main:app*") { Stop-Process -Id $_.Id -Force }
}
```

### macOS/Linux
```bash
if [ -f <workspace>/api/.api-pid ]; then
    kill $(cat <workspace>/api/.api-pid) 2>/dev/null
    rm <workspace>/api/.api-pid
fi
pkill -f "uvicorn main:app" || true
```

---

## Helper Scripts (Windows)

This skill includes PowerShell helper scripts:

| Script | Purpose |
|--------|---------|
| [start-api.ps1](./start-api.ps1) | Start API in persistent process |
| [stop-api.ps1](./stop-api.ps1) | Stop API and cleanup |
| [smoke-test.ps1](./smoke-test.ps1) | Run all smoke tests |

Usage: `& "<workspace>\.github\skills\validate-changes\start-api.ps1" -WorkspacePath "<workspace>"`

---

## Quick Reference

### Windows Commands

| Task | Command |
|------|---------|
| Kill API | `Stop-Process -Id (Get-Content .api-pid) -Force` |
| Lint | `uv run ruff check <file>` |
| Lint + fix | `uv run ruff check --fix <file>` |
| Format check | `uv run ruff format --check <file>` |
| Format fix | `uv run ruff format <file>` |
| Type check | `uv run ty check <file>` |
| Health check | `(Invoke-WebRequest http://localhost:8000/health -UseBasicParsing).Content` |

### macOS/Linux Commands

| Task | Command |
|------|---------|
| Kill API | `pkill -f "uvicorn main:app"` |
| Lint | `uv run ruff check <file>` |
| Lint + fix | `uv run ruff check --fix <file>` |
| Format check | `uv run ruff format --check <file>` |
| Format fix | `uv run ruff format <file>` |
| Type check | `uv run ty check <file>` |
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
| /health/detailed | ✅ 200 | database: true |
| /ready | ✅ 200 | ready |
| /openapi.json | ✅ 200 | Valid JSON |

### 6. Cleanup
✅ API process killed
```

---

## Common Issues

### Windows: API dies when running next command

**Cause**: Background processes in VS Code terminal get killed when new commands run.

**Solution**: Use `Start-Process` to spawn a separate PowerShell window (see Step 4).

### Windows: "uvicorn not found"

**Cause**: Running `uv run uvicorn` outside the venv context.

**Solution**: Either activate venv first, or use `python -m uvicorn`:
```powershell
.\.venv\Scripts\Activate.ps1; python -m uvicorn main:app --port 8000
```

### Port 8000 already in use

**Cause**: Previous API process wasn't cleaned up.

**Solution**: Run Step 0 cleanup commands, or use:
```powershell
# Windows - find and kill process on port 8000
Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue |
    ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }
```

---

## Trigger Phrases

- "validate changes"
- "run ruff and ty"
- "check this file"
- "lint and type check"
- "test the api"
- "start the api"
- "verify my changes"
