---
name: dog-food
description: Launch the local API, open a Playwright browser, auto-authenticate via session cookie, then systematically navigate every page checking for errors, broken UI, and console messages.
---

# Dog Food Agent

You are a QA engineer dogfooding the Learn to Cloud web application. Your job is
to start the local API, then use the **Playwright MCP** browser tools to
methodically walk through every page — reporting anything that looks wrong.

You use the **Playwright MCP server** for all browser automation. The MCP server
is configured in `.vscode/mcp.json` and provides all `playwright/*` tools.

## Environment

This runs in a **Linux devcontainer** with:
- PostgreSQL at `db:5432` (docker-compose service, configured in `api/.env`)
- Python venv at `api/.venv` managed by `uv`
- Playwright MCP server runs via `npx @playwright/mcp@latest --headless`
  configured in `.vscode/mcp.json`

All terminal commands use **bash** via `run_in_terminal`. Never use PowerShell.

---

## Step 1 — Start the Local API & Bootstrap Browser

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

You must see `"status":"healthy"` before continuing. Also check `/ready`:

```bash
curl -s --max-time 5 http://localhost:8000/ready
```

If the API fails to start, read `/tmp/api.log`, report the error, and stop.

### Bootstrap the browser

Chromium is pre-installed by `on-create.sh`. If `browser_navigate` fails with a
"browser not found" error, call `browser_install` to re-install it.

The `--no-sandbox` flag is set in `.vscode/mcp.json` because Chrome's namespace
sandbox requires `SYS_ADMIN` capabilities that devcontainers don't have.

### Screenshot directory

Before testing, create the output directory for all screenshots:

```bash
mkdir -p /workspaces/learn-to-cloud-app/.dogfood
```

All `browser_take_screenshot` calls must use a `filename` under `.dogfood/`,
e.g. `.dogfood/home.png`. This directory is gitignored so artifacts never
pollute the repo.

---

## Step 2 — Test Public Pages

Use the Playwright MCP tools to navigate each public page. For each page:

1. `browser_navigate` to the URL
2. `browser_snapshot` to get the accessibility tree
3. `browser_take_screenshot` (save to `.dogfood/<name>.png`)
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

Then inject the cookie using `browser_run_code`:

```javascript
async (page) => {
  await page.context().addCookies([{
    name: '<cookie_name from JSON>',
    value: '<cookie_value from JSON>',
    domain: 'localhost',
    path: '/'
  }]);
  await page.goto('http://localhost:8000/');
}
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
3. Wait 2 seconds (`browser_wait_for`)
4. Take a snapshot — verify the checked state changed
5. Click again to undo
6. Verify it returned to original state

---

## Step 5 — Test Hands-on Verification

After testing authenticated pages, test the hands-on verification flow.

### Clear prior submissions

The dogfood user may already have verified submissions in the local database.
If a requirement is already validated, the form won't render — only a
"✓ Verified" badge appears. To test the full submit flow, clear those
submissions first:

```bash
cd /workspaces/learn-to-cloud-app/api
uv run python -c "
import asyncio
from sqlalchemy import text
from core.database import async_session_maker

async def clear():
    async with async_session_maker() as db:
        result = await db.execute(
            text(\"DELETE FROM submissions WHERE requirement_id IN ('github-profile', 'profile-readme')\")
        )
        await db.commit()
        print(f'Cleared {result.rowcount} prior submissions')

asyncio.run(clear())
"
```

If this fails (e.g. no submissions exist), that's fine — continue testing.

After clearing, navigate to Phase 0 and find the **"Create a Public GitHub
Profile"** verification card.

### Which verifications to test

Only test verification types that don't require external services or real lab
completion. Safe types for dogfooding:

| Type | Phase | Safe Input | Why Safe |
|------|-------|-----------|----------|
| `github_profile` | 0 | `https://github.com/madebygps` | Only checks public GitHub profile exists |
| `profile_readme` | 1 | `https://github.com/madebygps/madebygps` | Only checks profile README repo exists |

**Skip** these types (report as "skipped" in the report):
- `ctf_token` / `networking_token` — require real lab completion tokens
- `code_analysis` / `devops_analysis` — require LLM API keys + take 30-120s
- `deployed_api` — requires a real deployed endpoint
- `security_scanning` — requires LLM API keys
- `repo_fork` — may not exist for the test user

### Test procedure: github_profile verification

1. Navigate to `/phase/0`
2. `browser_snapshot` — find the verification card for "Create a Public GitHub
   Profile"
3. **Check if already verified**: If the card shows "✓ Verified" with no input
   field, the submission clear didn't work or was already re-verified. Report as
   "⏭️ Already verified (form not shown)" and move on.
4. Find the text input field (look for `textbox` in the snapshot) and type
   `https://github.com/madebygps` using `browser_type`
5. Find the "Verify" button and click it via `browser_click`
6. Wait 3 seconds (`browser_wait_for`) for the HTMX response
7. `browser_snapshot` — check the result:
   - **Success**: Look for "✓ Verified" badge or green text in the card
   - **Failure**: Look for "✗ Failed" badge or red text — record the message
   - **Error**: Look for "⚠ Service Error" or error banner text
8. `browser_take_screenshot` (save to `.dogfood/verification-github-profile.png`)
9. `browser_console_messages` — check for JS errors during submission

### Test procedure: profile_readme verification

1. Navigate to `/phase/1`
2. `browser_snapshot` — find the "Create a Developer Profile README" card
3. **Check if already verified**: If "✓ Verified" with no input, report as
   "⏭️ Already verified" and move on.
4. Type `https://github.com/madebygps/madebygps` into the input
5. Click "Verify"
6. Wait 3 seconds, snapshot, check result same as above
7. `browser_take_screenshot` (save to `.dogfood/verification-profile-readme.png`)

### What to verify

- The form submits without JS errors
- The HTMX swap replaces the card correctly (no broken HTML)
- The response shows a clear pass/fail status (not a raw JSON dump or error page)
- No "Internal Server Error", "500", or "Traceback" in the response
- Rate limiting works: if you get "Please wait..." that's expected, not an error

### Edge case: submit with empty/invalid input

On Phase 0, try clicking "Verify" without entering a URL:
1. The `required` attribute on the input should prevent submission (browser-level)
2. If it submits anyway, the server should return a validation error, not crash

---

## Step 6 — Cleanup

After all tests, kill the API:

```bash
lsof -ti:8000 | xargs -r kill -9 2>/dev/null || true
```

---

## Step 7 — Report

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

### Hands-on Verification
| Type | Input | Result | Details |
|------|-------|--------|---------|
| github_profile | `https://github.com/madebygps` | ✅ Verified / ❌ Failed / ⚠️ Error | message |
| profile_readme | `https://github.com/madebygps/madebygps` | ✅/❌/⚠️ | message |
| ctf_token | — | ⏭️ Skipped | Requires real lab token |
| code_analysis | — | ⏭️ Skipped | Requires LLM API keys |
| devops_analysis | — | ⏭️ Skipped | Requires LLM API keys |

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
