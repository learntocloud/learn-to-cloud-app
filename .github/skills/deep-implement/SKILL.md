````skill
---
name: deep-implement
description: >
  Research-Plan-Implement workflow for non-trivial features.
  Deep-read the relevant code, write research.md, write plan.md,
  run annotation cycles with the user, then execute the full plan.
  Use when user says "deep implement", "plan and implement",
  "research and implement", "build feature", or describes a
  multi-step feature that needs architectural thought.
---

# Deep Implement — Research → Plan → Annotate → Implement

A disciplined workflow that separates **thinking from typing**.
Never write code until the user has reviewed and approved a written plan.

**Core principle:** Surface-level reading leads to surface-level implementations
that break the surrounding system. Every phase exists to prevent that.

---

## When to Use

- User describes a non-trivial feature (touches multiple files/modules)
- User says "deep implement", "plan and implement", "research this"
- User wants to add a feature that interacts with existing systems
- Any change where getting the architecture wrong would waste significant effort

**Do NOT use for:** Quick one-file fixes, formatting, typos, simple bug fixes.

---

## Phase 1: Research

**Goal:** Build deep understanding of the relevant code before proposing anything.

### Step 1.1: Identify Scope

Ask (or infer) which parts of the codebase are relevant:
- Which modules/folders/files?
- Which existing patterns does this interact with?
- Are there related features already implemented?

### Step 1.2: Deep Read

Read every relevant file thoroughly. Not just signatures — read function bodies,
understand data flow, note edge cases, understand error handling paths.

**Signal words matter:** Read "deeply", "in detail", "all the intricacies".
Do not skim. If a function calls another function, read that too.

For this codebase, typical areas to research:
- `api/routes/` — route definitions, dependencies, response patterns
- `api/services/` — business logic, verification flows
- `api/repositories/` — database access patterns, queries
- `api/core/` — config, auth, middleware, caching
- `api/models.py` — SQLAlchemy models, relationships
- `api/schemas.py` — Pydantic schemas
- `api/templates/` — Jinja2 templates, HTMX patterns
- `content/phases/` — content YAML files

### Step 1.3: Write research.md

Create `research.md` in the workspace root with:

```markdown
# Research: <Feature Name>

## Date
<current date>

## Relevant Files
- `path/to/file.py` — what it does, key functions
- ...

## How the Existing System Works
<detailed explanation of current behavior, data flow, patterns used>

## Key Patterns & Conventions
- <pattern 1>: how and where it's used
- <pattern 2>: ...

## Existing Code to Reuse
- <function/class>: can be extended for this feature
- ...

## Potential Pitfalls
- <pitfall 1>
- <pitfall 2>

## Open Questions
- <anything unclear that the user should weigh in on>
```

### Step 1.4: Present Research

Tell the user: **"I've written my research findings to research.md — please
review it and let me know if anything is wrong or missing before I write the
plan."**

**STOP. Wait for the user to confirm the research is accurate.**

If the user corrects something, update research.md and re-present.

---

## Phase 2: Planning

**Goal:** Produce a detailed, annotatable implementation plan.

### Step 2.1: Write plan.md

Create `plan.md` in the workspace root with:

```markdown
# Plan: <Feature Name>

## Overview
<1-2 paragraph summary of what will be built and why>

## Approach
<detailed explanation of the implementation approach, trade-offs considered>

## Changes

### 1. <First change area>
**File:** `path/to/file.py`
**What:** <description>

```python
# Code snippet showing the actual change
```

### 2. <Second change area>
...

## Database Changes
<migrations needed, if any — use `alembic revision --autogenerate -m "..."`)>

## Schema Changes
<new Pydantic models or changes to existing ones>

## Considerations
- <trade-off 1>
- <trade-off 2>

## What This Does NOT Change
<explicitly list things that stay the same — helps catch wrong assumptions>
```

**Include actual code snippets** — not pseudocode. The plan should show real
imports, real function signatures, real SQL. Base everything on the actual
codebase from the research phase.

### Step 2.2: Present Plan

Tell the user: **"I've written the implementation plan to plan.md — please
review it. Add inline notes directly in the file to correct anything, reject
approaches, or add constraints. Then tell me to update the plan."**

**STOP. Do not implement yet. Wait for the user.**

---

## Phase 3: Annotation Cycle (repeat 1-6x)

**Goal:** Inject the user's judgement and domain knowledge into the plan.

### When the User Says "I added notes" or "update the plan"

1. Re-read `plan.md` completely
2. Find all user annotations (look for notes that differ from what you wrote)
3. Address every single note — update the plan accordingly
4. Tell the user the plan has been updated
5. **STOP. Do not implement yet. Wait for confirmation.**

### Common User Annotations to Expect

- "not optional" — change a parameter from optional to required
- "use X instead of Y" — swap a library/pattern/approach
- "remove this section" — cut scope
- "this should be a PATCH not PUT" — correct HTTP semantics
- "the queue already handles retries" — domain knowledge
- Business constraints, naming preferences, UX requirements

### When the User is Satisfied

They'll say something like "looks good", "implement it", "go ahead".
Proceed to Step 3.1.

### Step 3.1: Add Todo List

Before implementing, add a task breakdown to plan.md:

```markdown
## Todo

- [ ] Phase 1: <description>
  - [ ] Task 1.1
  - [ ] Task 1.2
- [ ] Phase 2: <description>
  - [ ] Task 2.1
  - [ ] Task 2.2
- [ ] Phase 3: Tests
  - [ ] Task 3.1
```

Tell the user: **"I've added a detailed todo list to the plan. Ready to
implement?"**

**STOP. Wait for final go-ahead.**

---

## Phase 4: Implementation

**Goal:** Execute the plan mechanically. All creative decisions were made in Phases 1-3.

### Step 4.1: Execute

Implement everything in the plan. Follow these rules:

1. **Implement ALL tasks** — do not cherry-pick or skip
2. **Mark tasks as completed** in plan.md as you go (`- [x]`)
3. **Do not stop** until all tasks and phases are completed
4. **Do not add unnecessary comments** — keep the code clean
5. **Follow existing patterns** — match the style of surrounding code
6. **Run validation continuously** — after each significant change:

```bash
cd <workspace>/api && uv run ruff check <changed_files>
cd <workspace>/api && uv run ruff format --check <changed_files>
cd <workspace>/api && uv run ty check <changed_files>
```

7. **For Python files**: Follow the project conventions:
   - Use `uv run` for all Python commands
   - Repository pattern for DB access
   - Service layer for business logic
   - Pydantic schemas for validation
   - FastAPI dependencies for auth/rate-limiting

### Step 4.2: Handle Implementation Corrections

During implementation, the user may give terse corrections:

- "You didn't implement X" → go implement X
- "Move this to the service layer" → refactor as directed
- "This should match the pattern in users_routes.py" → read that file and match it
- "wider" / "still cropped" / "there's a gap" → for template/CSS changes, iterate

**Do NOT ask for clarification on terse corrections.** The plan provides all
the context needed — just execute.

### Step 4.3: When Something Goes Wrong

If the user says "I reverted everything" or "start over":
1. Acknowledge the revert
2. Ask for narrowed scope
3. Re-implement only what the user specifies

**Do NOT try to patch a bad approach.** Revert and re-scope.

---

## Phase 5: Validate

After all tasks are complete, run the full validation skill:

### Step 5.1: Lint & Type Check

```bash
cd <workspace>/api && uv run ruff check .
cd <workspace>/api && uv run ruff format --check .
cd <workspace>/api && uv run ty check .
```

### Step 5.2: Start API & Smoke Test

```bash
pkill -f "uvicorn main:app" || true
cd <workspace>/api && uv run python -m uvicorn main:app --host 127.0.0.1 --port 8000 &
sleep 3
curl -s http://localhost:8000/health
curl -s http://localhost:8000/ready
curl -s http://localhost:8000/openapi.json | head -c 200
```

### Step 5.3: Run Tests

```bash
cd <workspace>/api && uv run pytest tests/ -x --timeout=30
```

### Step 5.4: Cleanup

```bash
pkill -f "uvicorn main:app" || true
```

### Step 5.5: Update Plan

Mark the validation phase as complete in plan.md. Present a summary:

```markdown
## Completion Summary

### What was built
- <bullet list of changes>

### Files modified
- `path/to/file.py` — <what changed>

### Validation results
- Ruff lint: ✅
- Ruff format: ✅
- ty type check: ✅
- API startup: ✅
- Smoke tests: ✅
- Tests: ✅ (X passed)
```

---

## Artifact Lifecycle

| File | Created | Survives | Purpose |
|------|---------|----------|---------|
| `research.md` | Phase 1 | Until user deletes | Review surface for understanding |
| `plan.md` | Phase 2 | Until user deletes | Source of truth for implementation |

**These files are working documents.** They live in the workspace root and
should be `.gitignore`d (they're not production code).

---

## Quick Reference

| Phase | Trigger | Output | Gate |
|-------|---------|--------|------|
| Research | "deep implement <feature>" | `research.md` | User confirms research is accurate |
| Plan | Auto after research approved | `plan.md` | User reviews plan |
| Annotate | "I added notes" / "update the plan" | Updated `plan.md` | User says "looks good" |
| Todo | Auto after plan approved | Todo list in `plan.md` | User says "go" / "implement" |
| Implement | User green-lights | Code changes + updated `plan.md` | All tasks checked off |
| Validate | Auto after implementation | Validation results | All checks pass |

---

## Anti-Patterns to Avoid

- **Skimming code** — read deeply, not just signatures
- **Implementing before plan approval** — the "don't implement yet" guard is essential
- **Ignoring user annotations** — every note must be addressed
- **Adding scope during implementation** — the plan is the scope
- **Verbose code comments** — the plan documents the "why", code should be clean
- **Asking for permission at every step** — only gate at phase transitions

---

## Trigger Phrases

- "deep implement"
- "plan and implement"
- "research and implement"
- "research this feature"
- "build feature"
- "I need to add <complex feature>"
- "plan this out first"
````
