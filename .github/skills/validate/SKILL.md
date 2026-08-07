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

For workflow changes that add a Python command, also run that exact command
with only the environment variables supplied by the workflow. Do not assume
the devcontainer's environment is available in CI.

Fix root causes and rerun the failed gate. Do not suppress lint or type errors.
