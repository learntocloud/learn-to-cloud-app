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

---

## When to Use

- User says "review file" or "review this file" on a `.py` file
- User asks to "analyze imports" or "explain the patterns"
- User wants to understand libraries used in Python code

---

## Phase 1: Inventory

### Step 1.1: Extract All Imports

Read the file and categorize imports into:
- **Standard Library** — what each is used for
- **Third-Party Libraries** — library name + doc URL (see lookup table below)
- **Local Imports** — module path

### Step 1.2: Identify Patterns

List all patterns used: decorators, design patterns (Repository, Factory), async patterns, ORM patterns.

---

## Phase 2: Deep Library Research (MANDATORY)

**For EACH third-party library, complete ALL of the following.**

### Step 2.1: Fetch Official Documentation

Use `fetch_webpage` or `mcp_tavily_tavily_extract` to retrieve the specific docs page for the feature being used.

#### Documentation URL Lookup Table

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

### Step 2.2: Search Best Practices

Use `mcp_tavily_tavily_search` for each library:
- `"[library] [specific feature] best practices"`
- `"[library] [specific feature] gotchas"`

### Step 2.3: Audit Codebase Usage

Use `list_code_usages` and `grep_search` to find ALL usages of the library/function in the codebase. Check for consistency across files.

---

## Phase 3: Analysis & Findings

For each library, compare documented behavior against actual implementation. Focus on:

- **Parameter correctness** — are we passing the right args?
- **Edge case handling** — does the code handle documented failure modes?
- **Return value handling** — are we using results correctly?
- **Exception behavior** — are documented exceptions caught where needed?
- **Deprecated usage** — are we using current API, not legacy?

Cross-reference callers and models to verify alignment (e.g., `index_elements` in upserts match actual unique constraints).

---

## Phase 4: Report

For each issue found, provide:
- **Severity**: 🔴 Critical / 🟠 Medium / 🟡 Low
- **Location**: file + line
- **Problem**: what's wrong
- **Evidence**: quote from docs or best practice source with URL
- **Impact**: what could go wrong in production
- **Fix**: concrete code change

For files with 3+ third-party libraries, consider using `runSubagent` to parallelize doc fetching and best practice searches.

---

## Trigger Phrases

- "review file"
- "review this file"
- "analyze this Python file"
- "deep dive into this code"
- "audit this implementation"
