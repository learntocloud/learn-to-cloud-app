# General Project Context

## API Contract

The full OpenAPI 3.1 specification is committed at `api/openapi.json`. Use this as the source of truth for:

- All API endpoints, methods, and paths
- Request/response schemas (Pydantic models)
- Query parameters and path parameters
- Validation rules and constraints

When working on frontend API calls or backend routes, reference `api/openapi.json` for accurate type information and endpoint contracts.

**Regenerate after API changes:**
```bash
cd api && uv run python scripts/export_openapi.py
```
