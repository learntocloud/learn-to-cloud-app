---
applyTo: '**/*.py'
---

## Running the API

1. Navigate to the api directory first:
   ```bash
   cd /Users/gps/Developer/learn-to-cloud-app/api
   ```

2. Run the API using the venv python directly:
   ```bash
   .venv/bin/python -m uvicorn main:app --reload --port 8000
   ```

3. API will be available at:
   - Liveness: http://localhost:8000/health
   - Readiness: http://localhost:8000/ready
   - Swagger docs: http://localhost:8000/docs

## Virtual Environment

- Location: `api/.venv`
- Managed with `uv`
- To sync dependencies: `uv sync` (from api directory)
- To add packages: `uv add <package>` (from api directory)

## Common Issues

- **Port already in use**: Kill existing process first:
  ```bash
  pkill -f "uvicorn main:app"
  ```

- **Module not found errors**: Ensure you're using the venv python (`.venv/bin/python`), not system python

- **`uv run` not finding modules**: Use `.venv/bin/python -m uvicorn` instead of `uv run uvicorn`