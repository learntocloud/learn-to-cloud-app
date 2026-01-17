---
name: api-separation-review
description: Review API layer separation of concerns for models, schemas, repositories, services, and routes; produce a layer-grouped violation report with target files.
---

# Skill Instructions

## Goal
Perform a deep, API-only separation-of-concerns review. Identify mixed concerns and propose where each responsibility should live. Output a layer-grouped violation list with concrete target files.

## Layer Rules (Strict)
- Models: ORM definitions only. No business logic, HTTP logic, or schema logic.
- Schemas: API request/response validation only. No business configuration or service logic.
- Repositories: Database access only. No business rules, parsing of domain IDs, or cross-service orchestration.
- Services: Business logic and orchestration only. No HTTP request/response details or Pydantic return types.
- Routes: HTTP handling only. No business rules or data access.

## Workflow
1. Read layer guidelines in [api/services/__init__.py](api/services/__init__.py) and [api/repositories/__init__.py](api/repositories/__init__.py).
2. Review models in [api/models.py](api/models.py).
3. Review schemas in [api/schemas.py](api/schemas.py).
4. Review repositories in [api/repositories](api/repositories).
5. Review services in [api/services](api/services).
6. Review routes in [api/routes](api/routes).
7. Produce a layer-grouped violation report with target file suggestions.

## Output Format (Layer-Grouped)
- Models:
  - (Violation summary) → Target layer/file, with evidence link.
- Schemas:
  - (Violation summary) → Target layer/file, with evidence link.
- Repositories:
  - (Violation summary) → Target layer/file, with evidence link.
- Services:
  - (Violation summary) → Target layer/file, with evidence link.
- Routes:
  - (Violation summary) → Target layer/file, with evidence link.

## Evidence Links
When citing evidence, include file links with line ranges, e.g.:
- [api/repositories/progress.py](api/repositories/progress.py#L100-L120)

## Notes
- If new helpers are needed, place them under [api/services](api/services) using focused modules (e.g., validators or integrations).
- Services must not return Pydantic schemas; routes handle schema conversion.
