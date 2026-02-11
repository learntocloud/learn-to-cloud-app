```instructions
---
applyTo: "api/**/*.py"
description: "Logging, telemetry, and observability patterns for the FastAPI backend"
---

# Observability Guidelines

Simple approach: **stdlib logging** with structured `extra` fields, auto-instrumented
by **Azure Monitor + OpenTelemetry**.

---

## Quick Reference

| Need | Tool | Example |
|------|------|---------|
| Get a logger | `logging.getLogger(__name__)` | Module-level, one per file |
| Info event | `logger.info("event.name", extra={...})` | `logger.info("user.login", extra={"user_id": uid})` |
| Caught error | `logger.exception("event.name")` | Includes traceback automatically |
| Warning | `logger.warning("event.name", extra={...})` | Non-fatal issues |
| OTel tracing | Automatic via `configure_azure_monitor()` | Requests, SQLAlchemy, HTTP clients |

---

## 1. Logging Setup

`core/logger.py` provides `configure_logging()`, called once at startup in `main.py`.

- **Production**: JSON formatter (`_JSONFormatter`) — `extra` fields become queryable
  attributes in Application Insights `AppTraces`
- **Local dev**: Console formatter (`%(levelname)-5s [%(name)s] %(message)s`)
- Format is auto-selected based on `APPLICATIONINSIGHTS_CONNECTION_STRING`

### Logger per Module

```python
import logging

logger = logging.getLogger(__name__)
```

Every file that logs should declare this at module level. No wrapper function needed.

---

## 2. Structured Logging with `extra`

Pass context as an `extra` dict — never use f-strings for structured data.

```python
# ✅ Structured — queryable in App Insights
logger.info(
    "user.account_deleted",
    extra={"user_id": user_id, "github_username": github_username},
)

# ✅ Multiple context fields
logger.info(
    "phase_requirements.built",
    extra={"phases": len(requirements), "steps": total_steps},
)

# ❌ F-string — just text, loses structure
logger.info(f"User {user_id} deleted their account")
```

### Event Naming: `domain.action`

```python
# ✅ Good — dot-notation, lowercase
"user.account_deleted"
"step.completed"
"llm.semaphore.acquiring"
"auth.callback.token_exchange_failed"

# ❌ Bad
"Step completed successfully"  # Sentence, not queryable
"stepCompleted"                # CamelCase
```

### Errors with `logger.exception()`

Use in `except` blocks — automatically includes the traceback:

```python
try:
    result = await external_api.call()
except ExternalAPIError:
    logger.exception("external.api.failed")
    raise
```

---

## 3. Telemetry (Azure Monitor + OpenTelemetry)

Auto-instrumentation is configured in `main.py` via `_configure_observability()`,
which must run **before** FastAPI is imported.

### What's auto-traced (no code needed)

| Layer | Instrumentation |
|-------|----------------|
| **HTTP requests** | FastAPI auto-instrumentation → App Insights `AppRequests` |
| **SQL queries** | `instrument_sqlalchemy_engine()` → query spans with `sqlcommenter` |
| **Outbound HTTP** | `requests` / `urllib` / `urllib3` auto-instrumented |
| **LLM calls** | Agent Framework `enable_instrumentation()` traces LLM calls + token usage |

### `SecurityHeadersMiddleware`

`core/middleware.py` provides `SecurityHeadersMiddleware` (CSP, HSTS, X-Frame-Options, etc.)
and `UserTrackingMiddleware`, added in `main.py`'s middleware stack.

---

## 4. Complete Example

```python
import logging

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def complete_step(db: AsyncSession, user_id: str, step_id: str) -> StepProgress:
    """Mark a step as complete for a user."""
    step = await step_repo.get_step(db, step_id)
    if not step:
        logger.warning("step.not_found", extra={"step_id": step_id, "user_id": user_id})
        raise StepNotFoundError(step_id)

    progress = await progress_repo.mark_complete(db, user_id, step_id)

    badge = await check_badge_eligibility(db, user_id, step.phase_id)
    if badge:
        logger.info("badge.awarded", extra={"user_id": user_id, "badge_id": badge.id})

    logger.info(
        "step.completed",
        extra={
            "user_id": user_id,
            "step_id": step_id,
            "phase_id": step.phase_id,
            "first_completion": progress.completion_count == 1,
        },
    )
    return progress
```

---

## 5. Checklist for New Code

- [ ] Declare `logger = logging.getLogger(__name__)` at module level
- [ ] Use `extra={}` dicts for structured context, not f-strings
- [ ] Use dot-notation event names: `domain.action`
- [ ] Use `logger.exception()` in `except` blocks (auto-includes traceback)
- [ ] Include relevant IDs (`user_id`, `step_id`, etc.) in `extra`
- [ ] Don't add manual OTel spans — auto-instrumentation covers HTTP, SQL, and LLM calls
```
