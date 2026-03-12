---
name: dog-food
description: Launch the local API, open a Playwright browser, auto-authenticate via session cookie, then systematically navigate every page checking for errors, broken UI, and console messages.
---

# Dog Food Agent

You are a QA engineer dogfooding the Learn to Cloud web application. Your job is
to start the local API, then use the **Playwright MCP** browser tools to
methodically walk through every page — reporting anything that looks wrong.

You use the **Playwright MCP server** for all browser automation. The MCP server
is configured in `.vscode/mcp.json` and provides tools prefixed with
`mcp_playwright_browser_*`.

## Environment

This runs in a **Linux devcontainer** with:
- PostgreSQL at `db:5432` (docker-compose service, configured in `api/.env`)
- Python venv at `api/.venv` managed by `uv`
- Playwright MCP server runs via Docker image (`mcr.microsoft.com/playwright/mcp`)
  configured in `.vscode/mcp.json` — no npm/Playwright install needed in the container

All terminal commands use **bash** via `run_in_terminal`. Never use PowerShell.

---

## Step 1 — Start the Local API

Free port 8000 if in use, then start the API in background:

```bash
# Kill any existing API on port 8000
lsof -ti:8000 | xargs -r kill -9 2>/dev/null || true

# Start API in background
cd /workspaces/learn-to-cloud-app/api
nohup uv run uvicorn main:app --host 127.0.0.1 --port 8000 > /tmp/api.log 2>&1 &
```

Use `isBackground=true` for the API startup. Wait 5 seconds, then verify:

```bash
sleep 5 && curl -s --max-time 5 http://localhost:8000/health
```

You must see `"status":"healthy"` before continuing. If the API fails to start,
read `/tmp/api.log`, report the error, and stop.

---

## Step 2 — Test Public Pages

Use the Playwright MCP tools to navigate each public page. For each page:

1. `browser_navigate` to the URL
2. `browser_snapshot` to get the accessibility tree
3. `browser_take_screenshot` to capture visual state
4. `browser_console_messages` to check for errors
5. Verify `<nav>` and `<main>` elements exist in the snapshot
6. Check for error text ("Internal Server Error", "500", "404", "Traceback")

### Public pages to test

| Page | URL |
|------|-----|
| Home | `http://localhost:8000/` |
| Curriculum | `http://localhost:8000/curriculum` |
| FAQ | `http://localhost:8000/faq` |
| Privacy | `http://localhost:8000/privacy` |
| Terms | `http://localhost:8000/terms` |
| Status | `http://localhost:8000/status` |

### Dark mode

Find a button with "moon" or "sun" or "theme" text in the snapshot, click it,
take a snapshot to confirm the page changed.

---

## Step 3 — Authenticate via Session Cookie

Generate a signed session cookie for local auth bypass:

```bash
cd /workspaces/learn-to-cloud-app/api
uv run python ../scripts/dogfood_session.py
```

This prints JSON: `{"cookie_name": "session", "cookie_value": "...", "user_id": ..., "domain": "localhost", "path": "/"}`

Then use `browser_navigate` to a page and inject the cookie via JavaScript:

```
browser_navigate → http://localhost:8000/
```

Then navigate to an authenticated page. If redirected to login, the cookie didn't
work — report and skip authenticated tests.

**Important**: The `dogfood_session.py` script needs the database to be seeded
with at least one user. If it fails, skip authenticated tests.

---

## Step 4 — Test Authenticated Pages

After authentication, navigate and test:

| Page | URL | Verify |
|------|-----|--------|
| Dashboard | `/dashboard` | nav, main, username shown |
| Account | `/account` | nav, main, account settings visible |
| Phase 1 | `/phase/1` | nav, main, topic links present |
| First topic | First `/phase/1/*` link | Learning steps, checkboxes |

### Step toggle test

On a topic page:
1. Find a step checkbox in the snapshot
2. Click it via `browser_click`
3. Wait 2 seconds (`browser_wait`)
4. Take a snapshot — verify the checked state changed
5. Click again to undo
6. Verify it returned to original state

---

## Step 5 — Cleanup

After all tests, kill the API:

```bash
lsof -ti:8000 | xargs -r kill -9 2>/dev/null || true
```

---

## Step 6 — Report

Present results as a structured summary:

```
## 🐕 Dog Food Report

### Health
| Endpoint | Status |
|----------|--------|
| /health  | ✅/❌  |
| /ready   | ✅/❌  |

### Public Pages
| Page | Loaded | Console Errors | Issues |
|------|--------|----------------|--------|
| Home | ✅/❌  | none / list    | ...    |
| ...  | ...    | ...            | ...    |

### Authenticated Pages
| Page | Loaded | Console Errors | Issues |
|------|--------|----------------|--------|
| ...  | ...    | ...            | ...    |

### Interactions
| Test | Result |
|------|--------|
| Step toggle | ✅/❌ |
| Step undo   | ✅/❌ |
| Dark mode   | ✅/❌/N/A |

### Issues Found
1. ...
```

---

## Rules

- **Never stop on a single page failure** — record it and keep going.
- If auth fails, skip authenticated tests and report public results only.
- If the API won't start, stop immediately and report the startup error.
- Always clean up the API process when finished.
- Use `browser_snapshot` (accessibility tree) to understand page structure — it's
  faster and more reliable than screenshots for checking elements.
- Use `browser_take_screenshot` for visual quality assessment.
- Use `browser_console_messages` to catch JavaScript errors.
