---
name: review-api-routes
description: Deep dive review of FastAPI routes file - analyzes route ordering, HTTP semantics, OpenAPI documentation, dependencies, rate limiting, and response handling. Use when user says "review api", "review routes", "review endpoints" on a routes/*.py file.
---

# FastAPI Routes Deep Dive Review

**THIS IS NOT A SURFACE-LEVEL REVIEW.**

**SINGLE FILE FOCUS**: Review the ONE routes file the user specifies. Only read other files (services, schemas, frontend) when cross-referencing is needed to verify alignment.

For every route in **this file**, you MUST:
1. Verify HTTP method semantics (GET/POST/PUT/DELETE/PATCH)
2. Check route ordering for conflicts
3. Validate OpenAPI documentation completeness
4. Audit dependency injection patterns
5. Review response handling and status codes
6. Check rate limiting appropriateness

**Time/token budget**: This review is intentionally exhaustive.

---

## When to Use

- User says "review api", "review routes", or "review endpoints" on a `routes/*.py` file
- User asks about "API design" or "endpoint patterns"
- User wants to check route configuration
- File path contains `routes/` and ends in `.py`

**Scope**: ONE file at a time. If user has multiple routes files to review, they'll trigger this skill separately for each.

---

## PHASE 1: Route Inventory (Required First Step)

### Step 1.1: Extract All Routes

Read the file and create a comprehensive route table:

```markdown
## Route Inventory

| Order | Method | Path | Function | Auth | Rate Limit | Status Code | Response Model |
|-------|--------|------|----------|------|------------|-------------|----------------|
| 1 | GET | `/items` | `list_items` | Required | 30/min | 200 | `list[Item]` |
| 2 | POST | `/items` | `create_item` | Required | 10/min | 201 | `Item` |
| 3 | GET | `/items/{item_id}` | `get_item` | Optional | None | 200 | `Item` |
```

### Step 1.2: Identify Patterns

List all patterns used:
- Authentication (required, optional, none)
- Rate limiting strategies
- Dependency injection
- Response models
- Error handling

---

## PHASE 2: Route Ordering Analysis (CRITICAL)

**FastAPI matches routes in declaration order. Incorrect ordering causes routing bugs.**

> **Note**: Route ordering rules are also documented in `.github/instructions/python.instructions.md` (FastAPI Routes section).

### Step 2.1: Check for Routing Conflicts

Look for these dangerous patterns:

| Pattern | Example | Problem |
|---------|---------|---------|
| Parameterized before literal | `/{id}` before `/new` | `/new` matches as `id="new"` |
| Overlapping paths | `/users/{id}` and `/users/me` | Order matters |
| Catch-all routes | `/{path:path}` | Must be last |

### Step 2.2: Verify Correct Ordering

Routes MUST be ordered:
1. **Collection endpoints** (`/items`, `/items/search`)
2. **Literal paths** (`/items/me`, `/items/stats`, `/items/export`)
3. **Parameterized routes** (`/items/{id}`)
4. **Nested parameterized** (`/items/{id}/subitems`)

```markdown
### Route Ordering Analysis

| Current Order | Route | Type | Correct Position | Issue? |
|---------------|-------|------|------------------|--------|
| 1 | `GET /items/{id}` | Parameterized | Should be after literals | 🔴 Yes |
| 2 | `GET /items/stats` | Literal | Should be before `/{id}` | 🔴 Yes |
```

### Step 2.3: Check Frontend/Client Compatibility

If reordering is needed, verify frontend calls won't break:

```markdown
### Frontend Impact Analysis

Search for route usage in `frontend/src/**/*.ts`:

| Route | Frontend File | Hardcoded Path? | Will Break? |
|-------|---------------|-----------------|-------------|
| `GET /items/stats` | `api/items.ts` | Yes | No - path unchanged |
```

---

## PHASE 3: HTTP Semantics Review

> **Note**: Status code conventions are documented in `.github/instructions/python.instructions.md`. This phase verifies compliance and catches edge cases.

### Step 3.1: Method-Resource Alignment

Verify each route uses the correct HTTP method:

| Method | Purpose | Should Return | Idempotent? | Safe? |
|--------|---------|---------------|-------------|-------|
| GET | Read resource | Resource | Yes | Yes |
| POST | Create resource | Created resource | No | No |
| PUT | Replace resource | Updated resource | Yes | No |
| PATCH | Partial update | Updated resource | No | No |
| DELETE | Remove resource | Empty or deleted resource | Yes | No |

```markdown
### HTTP Semantics Check

| Route | Method | Action | Correct Method? | Issue |
|-------|--------|--------|-----------------|-------|
| `/items` | POST | Creates item | ✅ | - |
| `/items/{id}` | POST | Updates item | ❌ | Should be PUT or PATCH |
```

### Step 3.2: Status Code Validation

| Method | Success Code | Notes |
|--------|--------------|-------|
| GET | 200 | Resource found |
| POST (create) | **201** | Resource created |
| PUT/PATCH | 200 | Resource updated |
| DELETE | 204 | No content, or 200 with deleted resource |

```markdown
### Status Code Review

| Route | Method | Current Status | Expected | Issue? |
|-------|--------|----------------|----------|--------|
| `POST /items` | POST | 200 (default) | 201 | 🟠 Missing `status_code=201` |
```

---

## PHASE 4: OpenAPI Documentation Review

### Step 4.1: Fetch FastAPI OpenAPI Best Practices

Fetch: `https://fastapi.tiangolo.com/tutorial/response-model/`
Fetch: `https://fastapi.tiangolo.com/advanced/additional-responses/`

### Step 4.2: Response Documentation Checklist

| Check | Status | Notes |
|-------|--------|-------|
| All routes have `response_model` or return type | ✅/❌ | |
| Binary responses have `responses={200: {"content": {...}}}` | ✅/❌ | |
| Error responses documented (4xx, 5xx) | ✅/❌ | |
| `summary` and `description` provided | ✅/❌ | |
| Path parameters have descriptions | ✅/❌ | |
| Query parameters have descriptions | ✅/❌ | |

### Step 4.3: Binary Response Documentation

For endpoints returning non-JSON (PDF, PNG, etc.):

```python
# ❌ Missing OpenAPI documentation
@router.get("/export/pdf")
async def export_pdf():
    return Response(content=pdf_bytes, media_type="application/pdf")

# ✅ Properly documented
@router.get(
    "/export/pdf",
    responses={
        200: {
            "content": {"application/pdf": {"schema": {"type": "string", "format": "binary"}}},
            "description": "PDF document"
        }
    }
)
async def export_pdf():
    return Response(content=pdf_bytes, media_type="application/pdf")
```

---

## PHASE 5: Dependency Injection Review

### Step 5.1: Fetch FastAPI Dependencies Documentation

Fetch: `https://fastapi.tiangolo.com/tutorial/dependencies/`

### Step 5.2: Dependency Patterns Audit

```markdown
### Dependency Inventory

| Dependency | Type | Scope | Used In Routes | Pattern |
|------------|------|-------|----------------|---------|
| `DbSession` | `Annotated[AsyncSession, Depends(get_db)]` | Request | All | ✅ Modern |
| `UserId` | `Annotated[str, Depends(get_user_id)]` | Request | Auth routes | ✅ Modern |
| `Request` | `Request` | Request | Rate limited | ✅ |
```

### Step 5.3: Dependency Anti-Patterns

| Anti-Pattern | Example | Issue | Fix |
|--------------|---------|-------|-----|
| Raw `Depends()` in signature | `db: AsyncSession = Depends(get_db)` | Verbose, old style | Use `Annotated` type alias |
| Service instantiation in route | `service = MyService()` | No DI, hard to test | Inject via `Depends()` |
| Missing dependencies | Route accesses `request.state.user` | Implicit dependency | Make explicit with `Depends()` |

---

## PHASE 6: Rate Limiting Review

### Step 6.1: Rate Limit Appropriateness

| Endpoint Type | Recommended Limit | Rationale |
|---------------|-------------------|-----------|
| Read (GET list) | 30-60/min | Normal browsing |
| Read (GET single) | 60-100/min | Frequent access |
| Write (POST/PUT) | 10-30/min | Prevent spam |
| Expensive (PDF generation) | 5-10/min | Resource intensive |
| Auth endpoints | 5-10/min | Prevent brute force |

```markdown
### Rate Limit Analysis

| Route | Current Limit | Recommended | Issue? |
|-------|---------------|-------------|--------|
| `POST /certificates` | None | 10/min | 🔴 Missing - expensive operation |
| `GET /certificates/{id}/pdf` | 10/min | 5/min | 🟡 Could be stricter |
```

### Step 6.2: Rate Limit Key Strategy

Verify rate limits use appropriate keys:

| Key Type | Use Case | Example |
|----------|----------|---------|
| IP-based | Unauthenticated endpoints | `limit("10/minute")` |
| User-based | Authenticated endpoints | `limit("10/minute", key_func=get_user_id)` |
| Combined | Premium features | Custom key function |

---

## PHASE 7: Response Handling Review

### Step 7.1: Model Conversion Patterns

Check for redundant conversions:

```python
# ❌ Redundant conversion
return CertificateResponse.model_validate(certificate.model_dump())

# ✅ Direct conversion (Pydantic v2)
return CertificateResponse.model_validate(certificate)

# ✅ Or with from_attributes=True in model config
return CertificateResponse.from_orm(certificate)
```

### Step 7.2: Error Response Consistency

| Error Type | Expected Status | Expected Response |
|------------|-----------------|-------------------|
| Not found | 404 | `{"detail": "Resource not found"}` |
| Validation error | 422 | FastAPI automatic |
| Unauthorized | 401 | `{"detail": "Not authenticated"}` |
| Forbidden | 403 | `{"detail": "Not authorized"}` |
| Rate limited | 429 | `{"detail": "Rate limit exceeded"}` |

```markdown
### Error Handling Audit

| Route | Error Case | Current Handling | Correct? |
|-------|------------|------------------|----------|
| `GET /items/{id}` | Not found | Returns `None` | ❌ Should raise 404 |
| `POST /items` | Duplicate | Raises 500 | ❌ Should raise 409 |
```

---

## PHASE 8: Security Review

### Step 8.1: Authentication Requirements

```markdown
### Authentication Audit

| Route | Current Auth | Expected Auth | Issue? |
|-------|--------------|---------------|--------|
| `GET /items` | None | Required | 🔴 Unprotected |
| `GET /items/{id}` | Optional | Optional | ✅ |
| `POST /items` | Required | Required | ✅ |
| `DELETE /items/{id}` | Required | Required + Owner | 🟠 Missing ownership check |
```

### Step 8.2: Input Validation

| Check | Status | Notes |
|-------|--------|-------|
| Path parameters validated (type, range) | ✅/❌ | |
| Query parameters have constraints | ✅/❌ | |
| Request body uses Pydantic models | ✅/❌ | |
| File uploads have size/type limits | ✅/❌ | |

---

## PHASE 9: Cross-Reference Verification (Read Other Files Only Here)

**Only read external files in this phase** - and only when needed to verify findings.

### Step 9.1: Service Layer Alignment

If issues were found, read the corresponding service file to verify:

```markdown
### Service Layer Check

| Route | Service Function | Exists? | Signature Match? |
|-------|------------------|---------|------------------|
| `GET /items` | `items_service.list_items()` | ✅ | ✅ |
| `POST /items` | `items_service.create_item()` | ✅ | ⚠️ Different params |
```

### Step 9.2: Schema Alignment

Verify request/response schemas match service layer:

```markdown
### Schema Alignment

| Route | Request Schema | Response Schema | Matches Service? |
|-------|----------------|-----------------|------------------|
| `POST /items` | `ItemCreate` | `ItemResponse` | ✅ |
```

---

## PHASE 10: Comprehensive Checklist

| Category | Check | Status |
|----------|-------|--------|
| **Route Ordering** | No parameterized routes before literals | ✅/❌ |
| **Route Ordering** | Collection endpoints first | ✅/❌ |
| **HTTP Semantics** | Correct methods for actions | ✅/❌ |
| **HTTP Semantics** | POST returns 201 | ✅/❌ |
| **HTTP Semantics** | DELETE returns 204 or 200 | ✅/❌ |
| **OpenAPI** | All routes documented | ✅/❌ |
| **OpenAPI** | Binary responses documented | ✅/❌ |
| **OpenAPI** | Error responses documented | ✅/❌ |
| **Dependencies** | Uses `Annotated` pattern | ✅/❌ |
| **Dependencies** | No service instantiation in routes | ✅/❌ |
| **Rate Limiting** | Expensive operations limited | ✅/❌ |
| **Rate Limiting** | Appropriate limits per endpoint | ✅/❌ |
| **Response** | No redundant model conversions | ✅/❌ |
| **Response** | Consistent error responses | ✅/❌ |
| **Security** | Auth required where needed | ✅/❌ |
| **Security** | Input validation present | ✅/❌ |

---

## Output Format Requirements

1. **Tables for every analysis** - structured comparisons are essential
2. **Route order diagram** - visual representation of current vs recommended order
3. **Severity indicators**: 🔴 Critical, 🟠 Medium, 🟡 Low, ✅ Good, ❌ Issue
4. **Code examples** - show before/after for all fixes
5. **Frontend impact** - always check for breaking changes before recommending reordering

---

## Suggested Fixes Format

```markdown
## Suggested Fixes

### Fix [N]: [Title]

**Severity**: 🔴/🟠/🟡

**Location**: `routes/items_routes.py` line X

**Problem**:
Description.

**Before**:
```python
# current code
```

**After**:
```python
# fixed code
```

**Why**:
- Cite FastAPI docs: "..."
- Cite HTTP spec: "..."

**Breaking Changes**: None / List affected clients
```

---

## Execution Strategy

### Single File Focus

1. **Primary**: Analyze the ONE routes file the user specified
2. **Cross-reference only when needed**: Read services/schemas/frontend only to verify specific findings
3. **Don't expand scope**: If other routes files have issues, note them but don't review in detail

### Research Order

1. **First**: Inventory all routes in THIS file (method, path, function, decorators)
2. **Second**: Analyze route ordering for conflicts within THIS file
3. **Third**: Fetch FastAPI docs for specific patterns used
4. **Fourth**: (If reordering needed) Check frontend for breaking changes
5. **Fifth**: Review each route against checklists
6. **Sixth**: (If issues found) Cross-reference services/schemas to verify
7. **Seventh**: Compile findings and fixes

### When to Read Other Files

| Situation | File to Read | Why |
|-----------|--------------|-----|
| Recommending route reorder | `frontend/src/api/*.ts` | Check for hardcoded paths |
| Service function mismatch suspected | `services/*_service.py` | Verify function exists/signature |
| Schema issue suspected | `schemas.py` | Verify model fields |
| Router order matters | `main.py` | Check registration order |

**DO NOT** read other files "just to be thorough" - only when a specific finding requires verification.

---

## Example Trigger Phrases

- "review api"
- "review routes"
- "review endpoints"
- "check this routes file"
- "api design review"
- "audit these endpoints"
- "review this fastapi file"
