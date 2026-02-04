---
applyTo: "**/*.py"
description: "FastAPI routes, async patterns, structlog logging, SQLAlchemy, httpx clients, TTLCache caching"
---

# Python Coding Standards

## Separation of Concerns (CRITICAL)

### Layer Responsibilities
| Layer | Responsibility | What it DOES | What it does NOT do |
|-------|----------------|--------------|---------------------|
| **Routes** (`routes/`) | HTTP handling | Validate input, call services, return responses, raise `HTTPException` | Business logic, direct DB access, logging business events |
| **Services** (`services/`) | Business logic | Orchestrate operations, enforce rules, log domain events, raise domain exceptions | HTTP concerns, direct SQL, commit transactions |
| **Repositories** (`repositories/`) | Data access | Execute queries, return models/DTOs | Business rules, HTTP exceptions, commit transactions |


## Feedback
If you encounter a pattern, convention, or edge case that should be added to these instructions, let me know so we can consider including it.
