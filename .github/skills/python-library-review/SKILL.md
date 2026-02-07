---
name: python-library-review
description: Deep dive review of Python file - fetches official docs, searches best practices, audits all usages in codebase. Use when user says "review file", "review this file", or "analyze this code" on a .py file. This is NOT a surface-level review.
---

# Python Library & Pattern Deep Dive Review

**THIS IS NOT A SURFACE-LEVEL REVIEW.**

For every third-party library in the file, you MUST:
1. Fetch official documentation
2. Search for best practices and common pitfalls
3. Find all usages in the codebase
4. Compare documented behavior against actual implementation
5. Cite sources for every claim

**Time/token budget**: This review is intentionally exhaustive. It may take significant time and tokens. That is expected and correct.

---

## When to Use

- User says "review file" or "review this file" on a `.py` file
- User asks to "analyze imports" or "explain the patterns"
- User wants to understand libraries used in Python code

---

## PHASE 1: Inventory (Required First Step)

### Step 1.1: Extract All Imports

Read the file and create a categorized list:

```markdown
## Import Inventory

### Standard Library
| Import | Used For |
|--------|----------|
| `typing.Any` | Type hints |

### Third-Party Libraries (REQUIRE DEEP RESEARCH)
| Import | Library | Doc URL |
|--------|---------|---------|
| `sqlalchemy.ext.asyncio.AsyncSession` | SQLAlchemy | https://docs.sqlalchemy.org/en/20/ |

### Local Imports
| Import | File Path |
|--------|-----------|
| `models.User` | `api/models.py` |
```

### Step 1.2: Identify Patterns

List all patterns used:
- Decorators (`@decorator`)
- Design patterns (Repository, Factory, etc.)
- Async patterns (async/await, context managers)
- ORM patterns (sessions, transactions, upserts)

---

## PHASE 2: Deep Library Research (MANDATORY)

**For EACH third-party library identified, you MUST complete ALL of the following steps. Do not skip any.**

### Step 2.1: Fetch Official Documentation

Use `fetch_webpage` or `mcp_tavily_tavily_extract` to retrieve official docs.

**Common Documentation URLs:**

### This Project's Stack

| Library | Documentation URL |
|---------|-------------------|
| SQLAlchemy 2.0 | `https://docs.sqlalchemy.org/en/20/` |
| SQLAlchemy PostgreSQL Dialect | `https://docs.sqlalchemy.org/en/20/dialects/postgresql.html` |
| SQLAlchemy Async | `https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html` |
| FastAPI | `https://fastapi.tiangolo.com/` |
| Pydantic v2 | `https://docs.pydantic.dev/latest/` |
| pydantic-settings | `https://docs.pydantic.dev/latest/concepts/pydantic_settings/` |
| httpx | `https://www.python-httpx.org/` |
| structlog | `https://www.structlog.org/en/stable/` |
| slowapi | `https://slowapi.readthedocs.io/en/latest/` |
| cachetools (TTLCache) | `https://cachetools.readthedocs.io/en/stable/` |
| authlib | `https://docs.authlib.org/en/latest/` |
| Jinja2 | `https://jinja.palletsprojects.com/en/stable/` |
| tenacity | `https://tenacity.readthedocs.io/en/latest/` |
| circuitbreaker | `https://pypi.org/project/circuitbreaker/` |
| asyncpg | `https://magicstack.github.io/asyncpg/current/` |
| CairoSVG | `https://cairosvg.org/documentation/` |
| Alembic | `https://alembic.sqlalchemy.org/en/latest/` |
| pytest | `https://docs.pytest.org/en/stable/` |
| respx | `https://lundberg.github.io/respx/` |
| factory-boy | `https://factoryboy.readthedocs.io/en/stable/` |

**For each library, fetch the SPECIFIC documentation page for the feature being used:**

```markdown
### Documentation Fetched

| Library Feature | URL Fetched | Key Findings |
|-----------------|-------------|--------------|
| `pg_insert.on_conflict_do_update` | https://docs.sqlalchemy.org/en/20/dialects/postgresql.html#insert-on-conflict-upsert | ... |
```

### Step 2.2: Search Best Practices (MANDATORY)

Use `mcp_tavily_tavily_search` to find best practices and pitfalls.

**Required searches for each library:**

```
"[library name] best practices 2024"
"[library name] common mistakes"
"[library name] [specific feature] gotchas"
"[library name] production tips"
```

**Example for SQLAlchemy upsert:**
```
"sqlalchemy on_conflict_do_update best practices"
"sqlalchemy upsert pitfalls async"
"postgresql ON CONFLICT DO UPDATE gotchas"
```

**Document findings:**

```markdown
### Best Practices Research

| Search Query | Source | Key Finding |
|--------------|--------|-------------|
| "sqlalchemy on_conflict_do_update best practices" | Stack Overflow / Blog | ... |
```

### Step 2.3: Audit Codebase Usage

Use `list_code_usages` and `grep_search` to find ALL usages of the library/function in the codebase.

```markdown
### Codebase Usage Audit

| Function/Class | File | Line | Usage Pattern | Matches Best Practice? |
|----------------|------|------|---------------|------------------------|
| `upsert_on_conflict` | submission_repository.py | 82 | Upsert with returning | ✅ |
```

**Verify consistency:**
- Are all usages following the same pattern?
- Are there any usages that contradict best practices?
- Are the parameters being passed correctly everywhere?

---

## PHASE 3: Library Behavior Analysis (Per Library)

For EACH third-party library, produce this analysis WITH CITATIONS:

```markdown
---

## [N]. `library.module.function` — Deep Dive

### Official Documentation Summary
> Direct quote or paraphrase from official docs with URL citation.

**Source**: [URL]

### How It Actually Works

| Behavior | Documentation Says | Our Implementation | Match? |
|----------|-------------------|-------------------|--------|
| Parameter X | "Does Y" (source) | We pass Z | ✅/❌ |
| Edge case A | "Raises B" (source) | Not handled | ❌ |

### Documented Gotchas & Pitfalls

From official docs and best practice searches:

| Gotcha | Source | Applies to Our Code? | Mitigation |
|--------|--------|---------------------|------------|
| "Python-side defaults NOT applied on conflict update" | SQLAlchemy docs | ✅ Yes | Manually include `updated_at` |

### Best Practices Checklist

| Practice | Source | Our Code | Status |
|----------|--------|----------|--------|
| Always validate input before upsert | Blog X | Not done | ⚠️ |

### Parameter Deep Dive

| Parameter | Type | Required | Default | Our Usage | Correct? |
|-----------|------|----------|---------|-----------|----------|
| `index_elements` | `list[str]` | Yes | N/A | `["user_id", "requirement_id"]` | ✅ |

### Return Value Analysis

| Condition | Returns | Our Handling | Correct? |
|-----------|---------|--------------|----------|
| Success with `returning=True` | Model instance | `scalar_one()` | ✅ |
| Conflict with empty `set_` | Raises error | Not guarded | ❌ |

### Exception Behavior

| Exception | When Raised | Our Handling | Recommendation |
|-----------|-------------|--------------|----------------|
| `IntegrityError` | Constraint violation | Not caught | Document or catch |
```

---

## PHASE 4: Cross-Reference Verification

### Step 4.1: Model Constraint Verification

If the code references database models, READ the model definitions and verify:

```markdown
### Model Constraint Verification

| Code Reference | Model | Constraint in Model | Match? |
|----------------|-------|---------------------|--------|
| `index_elements=["user_id", "requirement_id"]` | `Submission` | `UniqueConstraint("user_id", "requirement_id")` | ✅ |
```

### Step 4.2: Caller Verification

Find all callers of the functions in this file and verify they use it correctly:

```markdown
### Caller Analysis

| Caller | File | Correct Parameters? | Handles Return? | Handles Errors? |
|--------|------|---------------------|-----------------|-----------------|
| `create_or_update_submission` | submission_repository.py | ✅ | ✅ | ⚠️ Uses assert |
```

---

## PHASE 5: Implementation Review

### Comprehensive Checklist

| Category | Check | Status | Evidence/Citation |
|----------|-------|--------|-------------------|
| **Library Usage** | Matches documented API | ✅/❌ | Doc URL + line number |
| **Library Usage** | Handles documented edge cases | ✅/❌ | Doc URL + line number |
| **Library Usage** | Follows best practices from search | ✅/❌ | Source URL |
| **Async Patterns** | Correct async/await usage | ✅/❌ | |
| **Async Patterns** | No blocking calls in async context | ✅/❌ | |
| **Type Hints** | All parameters typed | ✅/❌ | |
| **Type Hints** | Return type annotated | ✅/❌ | |
| **Type Hints** | Uses modern syntax (3.10+) | ✅/❌ | |
| **Error Handling** | Catches specific exceptions | ✅/❌ | |
| **Error Handling** | Handles all documented exceptions | ✅/❌ | Doc URL |
| **Imports** | Organized (stdlib → third-party → local) | ✅/❌ | |
| **Imports** | No unused imports | ✅/❌ | |

### Issues Found

For each issue, provide:

```markdown
### Issue [N]: [Title]

**Severity**: 🔴 Critical / 🟠 Medium / 🟡 Low

**Location**: `file.py` line X

**Problem**:
Description of what's wrong.

**Evidence**:
> Quote from documentation or best practice source proving this is an issue.

**Source**: [URL]

**Impact**:
What could go wrong in production.

**Recommended Fix**:
```python
# corrected code
```
```

---

## PHASE 6: Suggested Fixes

Provide complete, tested fixes for all issues found:

```markdown
## Suggested Fixes

### Fix [N]: [Title]

**Issue Reference**: Issue [N] above

**Before** (`file.py` line X):
```python
# exact code from file
```

**After**:
```python
# corrected code with explanation comments
```

**Why This Fix**:
- Cite documentation: "According to [source], ..."
- Cite best practice: "The recommended pattern from [source] is ..."

**Testing**:
- How to verify this fix works
- Edge cases to test
```

---

## Python-Specific Deep Dive Checklists

> **Note**: Basic standards are in `.github/instructions/python.instructions.md`. These checklists are for **deep verification during reviews**—fetch docs and compare actual behavior.

### SQLAlchemy Async (Verify Against Docs)

Fetch: `https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html`

- [ ] Uses `AsyncSession` (not sync `Session`)
- [ ] `begin_nested()` for savepoints when catching `IntegrityError`
- [ ] `flush()` inside transactions, `commit()` at boundaries
- [ ] No `commit()` inside repository methods
- [ ] `scalar_one()` vs `scalar_one_or_none()` used correctly
- [ ] Connection pool settings appropriate for async

### SQLAlchemy PostgreSQL (Verify Against Docs)

Fetch: `https://docs.sqlalchemy.org/en/20/dialects/postgresql.html`

- [ ] `on_conflict_do_update` has non-empty `set_`
- [ ] `index_elements` matches actual unique constraint
- [ ] `returning()` used correctly with async
- [ ] Python-side `onupdate` triggers handled manually

### FastAPI / Pydantic v2 (Verify Against Docs)

Fetch: `https://fastapi.tiangolo.com/` and `https://docs.pydantic.dev/latest/`

- [ ] Pydantic v2 syntax (`model_validator` not `@validator`)
- [ ] `Annotated[T, Depends(...)]` for dependencies (this project uses type aliases: `UserId`, `OptionalUserId`, `DbSession`, `DbSessionReadOnly` — defined in `core/auth.py` and `core/database.py`)
- [ ] Response models match return types
- [ ] Proper status codes for each endpoint
- [ ] HTMX routes use `response_class=HTMLResponse` (not `response_model`)

---

## Output Format Requirements

1. **Every claim about library behavior MUST have a citation** (URL or "Official docs")
2. **Use tables extensively** for structured comparisons
3. **Code blocks** with `python` syntax highlighting
4. **Emoji severity indicators**: 🔴 Critical, 🟠 Medium, 🟡 Low, ✅ Good, ❌ Issue, ⚠️ Warning
5. **Numbered sections** for each library deep dive
6. **Link to source files** using markdown links with line numbers

---

## Execution Strategy

### For Files with 3+ Third-Party Libraries

Consider using `runSubagent` to parallelize research:

```
Spawn a subagent to research [Library X]:
1. Fetch official docs for [specific feature]
2. Search for "[library] [feature] best practices"
3. Search for "[library] [feature] common mistakes"
4. Return: documented behavior, gotchas, best practices with URLs
```

### Research Order

1. **First**: Fetch all official documentation pages (can be parallel)
2. **Second**: Run all best practice searches (can be parallel)
3. **Third**: Audit codebase usages (sequential)
4. **Fourth**: Cross-reference and verify (sequential)
5. **Fifth**: Compile findings and fixes

---

## Example Trigger Phrases

- "review file"
- "review this file"
- "analyze this Python file"
- "deep dive into this code"
- "check the libraries in this file"
- "audit this implementation"
