---
name: review-api-routes
description: Deep dive review of FastAPI routes file - analyzes route ordering, HTTP semantics, OpenAPI documentation, dependencies, rate limiting, and response handling. Use when user says "review api", "review routes", "review endpoints" on a routes/*.py file.
---

# FastAPI Routes Deep Dive Review

**SINGLE FILE FOCUS**: Review the ONE routes file the user specifies. Only read other files when cross-referencing is needed to verify alignment.

---

## When to Use

- User says "review api", "review routes", or "review endpoints" on a `routes/*.py` file
- File path contains `routes/` and ends in `.py`

---

## Phase 1: Route Inventory

### Step 1.1: Extract All Routes

Read the file and create a route table:

| Order | Method | Path | Function | Auth | Rate Limit | Status Code | Response |
|-------|--------|------|----------|------|------------|-------------|----------|

### Step 1.2: Classify Route Type

| Route Type | Characteristics | Review Approach |
|-----------|----------------|-----------------|
| **JSON API** | `response_model=...`, Pydantic schemas, included in OpenAPI | Full OpenAPI + schema review |
| **HTMX** | `response_class=HTMLResponse`, `include_in_schema=False`, returns HTML fragments | Skip OpenAPI, verify templates. Input uses `Form(...)`, errors return inline HTML |
| **Pages** | `response_class=HTMLResponse`, `include_in_schema=False`, full pages via `TemplateResponse` | Skip OpenAPI, verify catch-all ordering |

---

## Phase 2: Route Ordering Analysis (CRITICAL)

**FastAPI matches routes in declaration order. Incorrect ordering causes routing bugs.**

### Dangerous Patterns

| Pattern | Example | Problem |
|---------|---------|---------|
| Parameterized before literal | `/{id}` before `/new` | `/new` matches as `id="new"` |
| Overlapping paths | `/users/{id}` and `/users/me` | Order matters |
| Catch-all routes | `/{path:path}` | Must be last |

### Correct Ordering

Routes MUST be ordered:
1. **Collection endpoints** (`/items`, `/items/search`)
2. **Literal paths** (`/items/me`, `/items/stats`)
3. **Parameterized routes** (`/items/{id}`)
4. **Nested parameterized** (`/items/{id}/subitems`)

If reordering is needed, check frontend templates for `hx-get`/`hx-post` references to ensure no breaking changes.

---

## Phase 3: Project-Specific Patterns

### Dependency Type Aliases

This project uses `Annotated` type aliases — verify routes use them instead of raw `Depends()`:

| Alias | Definition | Use For |
|-------|-----------|---------|
| `DbSession` | `Annotated[AsyncSession, Depends(get_db)]` | Write routes |
| `DbSessionReadOnly` | `Annotated[AsyncSession, Depends(get_db_readonly)]` | Read-only routes |
| `UserId` | `Annotated[int, Depends(require_auth)]` | Auth-required routes |
| `OptionalUserId` | `Annotated[int \| None, Depends(optional_auth)]` | Optional auth routes |

These are defined in `core/auth.py` and `core/database.py`.

### Rate Limiting

This project uses slowapi with a combined key function (`_get_request_identifier` in `core/ratelimit.py`):
- Authenticated: keyed by `user:{user_id}`
- Unauthenticated: keyed by IP
- Default limit: `100/minute` (when no explicit `@limiter.limit()`)

Recommended limits by endpoint type:

| Endpoint Type | Recommended Limit |
|---------------|-------------------|
| Read (GET list) | 30-60/min |
| Read (GET single) | 60-100/min |
| Write (POST/PUT) | 10-30/min |
| Expensive (PDF generation) | 5-10/min |
| HTMX interactions | 30-60/min |
| Verification submissions | 5-10/hour |

---

## Phase 4: Full Review

Review each route for:
- HTTP method semantics (GET reads, POST creates with 201, PUT/PATCH updates, DELETE returns 204)
- OpenAPI documentation (JSON API routes only — `response_model`, `summary`, documented error responses, binary response schemas)
- Auth requirements (correct level for each endpoint)
- Input validation
- Error response consistency (`{"detail": "..."}` for JSON, inline HTML for HTMX)
- No redundant model conversions (use `model_validate()` directly, not `model_validate(obj.model_dump())`)

---

## Phase 5: Cross-Reference (only when needed)

| Situation | File to Read | Why |
|-----------|--------------|-----|
| Recommending route reorder | `api/templates/**/*.html` | Check `hx-get`/`hx-post` references |
| Service mismatch suspected | `services/*_service.py` | Verify function exists/signature |
| Schema issue suspected | `schemas.py` | Verify model fields |
| Router order matters | `main.py` | Check registration order |

**Do NOT read other files "just to be thorough"** — only when a specific finding requires verification.

---

## Output Format

For each issue:
- **Severity**: 🔴 Critical / 🟠 Medium / 🟡 Low
- **Location**: file + line
- **Problem + Fix**: before/after code blocks
- **Breaking Changes**: note any affected clients/templates

---

## Trigger Phrases

- "review api"
- "review routes"
- "review endpoints"
- "review this fastapi file"
