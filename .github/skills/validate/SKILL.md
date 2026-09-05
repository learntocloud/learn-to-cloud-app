---
name: validate
description: Run the repository quality gate and smoke-test the API. Use after Python changes or for "validate changes", "run checks", or "test the API".
---

# Validate Changes

From the repository root run the authoritative quality gate:

```bash
uv run poe check
```

It runs static checks, package installation smoke testing, and all test suites.
New files must be staged before `prek --all-files` can inspect them; stage only
files belonging to the current task.

After Python application changes, start a fresh API process on
`127.0.0.1:8000` and request:

- `/health` (200)
- `/ready` (200 once dependencies are ready)
- `/openapi.json` (200 and valid JSON)

Track the exact process ID and always terminate that process during cleanup.
Do not kill unrelated listeners. Report startup logs if any endpoint fails.

For authentication or route-policy changes, preserve the real-route coverage in
`api/tests/routes/test_auth_http.py`: API/HTMX 401s, page 303s, redirect methods,
signed-session success, and repeatable logout. Do not bypass authentication
with dependency overrides when testing authentication itself. The same file
checks exported request spans; `api/tests/core/test_middleware.py` covers nested
router templates. These tests already run in `uv run poe check`.

See [Authentication and sessions](../../../docs/contributing.md#authentication-and-sessions)
for the response and session-lifecycle contract.

For workflow changes that add a Python command, also run that exact command
with only the environment variables supplied by the workflow. Do not assume
the local WSL environment is available in CI.

Fix root causes and rerun the failed gate. Do not suppress lint or type errors.
