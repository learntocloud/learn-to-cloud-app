```instructions
---
applyTo: "api/**/*.py"
description: "Logging, wide events, telemetry, and observability patterns for the FastAPI backend"
---

# Observability Guidelines

This codebase follows the **wide event / canonical log line** pattern.

**Core principle**: Instead of many sparse log lines per request, emit **one rich event**
with all context needed for debugging.

## The Mental Model Shift

> Instead of logging what your code is doing, log what happened to this request.

Traditional logging:
```python
# ❌ 5 separate log lines, impossible to correlate
logger.info("Processing checkout")
logger.info(f"User: {user_id}")
logger.info(f"Cart total: {total}")
logger.info("Payment processed")
logger.info("Checkout complete")
```

Wide event approach:
```python
# ✅ One event with full context, trivially queryable
set_wide_event_fields(
    user_id=user_id,
    cart_total_cents=total,
    payment_method="card",
    checkout_outcome="success",
)
# Middleware emits: request.completed {service, version, user_id, cart_total_cents, ...}
```

---

## Quick Reference

| Need | Tool | Example |
|------|------|---------|
| Request context | `set_wide_event_fields()` | `set_wide_event_fields(user_tier="premium")` |
| Nested context | `set_wide_event_nested()` | `set_wide_event_nested("grading", score=85)` |
| Errors/exceptions | `logger.exception()` | `logger.exception("payment.failed", provider="stripe")` |
| Discrete event | `logger.info()` | `logger.info("badge.awarded", badge_id="b1")` |
| Trace attribute | `add_custom_attribute()` | `add_custom_attribute("llm.model", "gemini")` |
| Metrics | `log_metric()` | `log_metric("questions.graded", 1)` |

---

## 1. Wide Events (Canonical Log Line)

The middleware automatically initializes wide events with request context:

```json
{
  "service_name": "learn-to-cloud-api",
  "service_version": "0.1.0",
  "request_id": "req_8bf7ec2d",
  "http_method": "POST",
  "http_path": "/api/steps/complete",
  "http_client_ip": "192.168.1.42",
  "outcome": "success"
}
```

**Your job**: Enrich with business context throughout the request.

### Add Business Context

```python
from core.wide_event import set_wide_event_fields, set_wide_event_nested

# In your route or service:
set_wide_event_fields(
    user_id=user.id,
    user_subscription="premium",
    step_id=step_id,
    phase_id=phase.id,
)

# For related data, use nested:
set_wide_event_nested("grading",
    score=85,
    attempts=2,
    topic="networking",
)
# Results in: {"grading": {"score": 85, "attempts": 2, "topic": "networking"}}
```

### What Context to Add (High Dimensionality)

| Category | Fields to Add |
|----------|---------------|
| **User** | `user_id`, `user_subscription`, `user_account_age_days`, `user_lifetime_value` |
| **Business** | `step_id`, `phase_id`, `badge_earned`, `quiz_score`, `scenario_topic` |
| **Feature flags** | `feature_flags.new_grading_flow`, `feature_flags.ai_hints_enabled` |
| **External calls** | `llm_model`, `llm_tokens_used`, `github_api_calls` |

### High Cardinality is GOOD

Fields like `user_id`, `request_id`, `trace_id` have millions of unique values.
**This is exactly what makes debugging possible.**

```python
# ✅ High cardinality - enables "show me all requests for user X"
set_wide_event_fields(user_id=user.id, session_id=session.id)

# ❌ Low cardinality only - useless for debugging specific issues
set_wide_event_fields(http_method="POST")  # Only 5 possible values
```

---

## 2. Tail Sampling (Automatic)

The middleware implements tail-based sampling:

| Condition | Sampled? | Reason |
|-----------|----------|--------|
| Status >= 400 | ✅ Always | Errors are rare and critical |
| Duration > 1000ms | ✅ Always | Slow requests indicate problems |
| `user_id` present | ✅ Always | Authenticated = business-relevant |
| Success + fast + anonymous | ⚠️ Sometimes | Happy path, sample to control costs |

**Your job**: Add `user_id` to wide event for authenticated requests so they're always logged.

```python
# In auth dependency or early in route:
set_wide_event_fields(user_id=current_user.id)
```

---

## 3. Structured Logging (For Errors & Discrete Events)

Use logger for things that happen WITHIN a request that deserve their own line:

```python
from core.logger import get_logger
logger = get_logger(__name__)

# ✅ Errors with stack traces
try:
    result = await external_api.call()
except ExternalAPIError as e:
    logger.exception("external.api.failed", service="stripe", endpoint="/charges")
    raise

# ✅ Discrete business events worth tracking individually
logger.info("badge.awarded", user_id=user_id, badge_id="phase_1_complete")
```

### Event Naming: `domain.action.result`

```python
# ✅ Good
"step.completed"
"badge.awarded"
"grading.failed"
"external.api.timeout"

# ❌ Bad
"Step completed successfully"  # Sentence, not queryable
"stepCompleted"                # CamelCase
```

### Keyword Arguments, Not F-Strings

```python
# ✅ Structured - queryable, aggregatable
logger.info("step.completed", user_id=user_id, step_id=step_id, duration_ms=45)

# ❌ F-string - just text, loses structure
logger.info(f"User {user_id} completed step {step_id} in 45ms")
```

---

## 4. Complete Example

```python
from core.logger import get_logger
from core.wide_event import set_wide_event_fields, set_wide_event_nested
from core.telemetry import add_custom_attribute, log_metric

logger = get_logger(__name__)


async def complete_step(db: AsyncSession, user_id: str, step_id: str) -> StepProgress:
    """Mark a step as complete for a user."""

    # Add user context early (ensures request is always logged)
    set_wide_event_fields(user_id=user_id, step_id=step_id)

    step = await step_repo.get_step(db, step_id)
    if not step:
        logger.warning("step.not_found", step_id=step_id, user_id=user_id)
        raise StepNotFoundError(step_id)

    # Add business context
    set_wide_event_fields(phase_id=step.phase_id, step_type=step.step_type)

    progress = await progress_repo.mark_complete(db, user_id, step_id)

    # Check for badge award
    badge = await check_badge_eligibility(db, user_id, step.phase_id)
    if badge:
        logger.info("badge.awarded", user_id=user_id, badge_id=badge.id)
        set_wide_event_fields(badge_awarded=badge.id)

    # Add outcome context
    set_wide_event_nested("completion",
        is_first=progress.completion_count == 1,
        total_completions=progress.completion_count,
    )

    # Emit metric for dashboards
    log_metric("steps.completed", 1, {"phase": step.phase_id})

    return progress
```

**Result**: One `request.completed` event with ~20 fields, enabling queries like:
- "Show me all step completions where a badge was awarded"
- "What's the completion rate by phase?"
- "Which steps take longest for premium users?"

---

## 5. Checklist for New Code

- [ ] Add `user_id` to wide event early (ensures request is logged)
- [ ] Add business context: IDs, outcomes, counts, flags
- [ ] Use `logger.exception()` for caught errors (includes traceback)
- [ ] Use dot-notation event names: `domain.action.result`
- [ ] Pass data as keyword args, not f-strings
- [ ] Add `@track_dependency` for external service calls
- [ ] Keep metric tags low-cardinality (no user IDs)

---

## References

- [loggingsucks.com](https://loggingsucks.com/) — The philosophy behind this approach
- [Honeycomb's Guide to Wide Events](https://www.honeycomb.io/blog/how-are-structured-logs-different-from-events)
- [Stripe's Canonical Log Lines](https://stripe.com/blog/canonical-log-lines)
```
