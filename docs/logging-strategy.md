# Logging Strategy

This document describes the logging and observability approach for the Learn to Cloud API.

## Overview

We use **Wide Events** (aka Canonical Log Lines) instead of scattered debug logs. Each HTTP request emits a single, context-rich structured log at completion containing all relevant information for debugging and analytics.

### Why Wide Events?

| Traditional Logging | Wide Events |
|---------------------|-------------|
| Multiple log lines per request | One log per request |
| Context scattered across logs | All context in one place |
| Hard to correlate | Easy to query by any field |
| String search | Structured queries |

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Request Lifecycle                         │
├─────────────────────────────────────────────────────────────┤
│  1. RequestTimingMiddleware initializes wide event          │
│     └─ http_method, http_path, http_client_ip               │
│                                                             │
│  2. Auth dependency enriches with user context              │
│     └─ user_id                                              │
│                                                             │
│  3. Route handlers add business context (optional)          │
│     └─ cart_id, step_id, topic_id, etc.                     │
│                                                             │
│  4. RequestTimingMiddleware emits wide event at end         │
│     └─ http_route, http_status_code, duration_ms, outcome   │
└─────────────────────────────────────────────────────────────┘
```

## Implementation

### Core Files

| File | Purpose |
|------|---------|
| `core/wide_event.py` | Context variable and helper functions |
| `core/telemetry.py` | Middleware that manages wide event lifecycle |
| `core/auth.py` | Enriches wide event with user_id |

### Adding Context in Routes

```python
from core import set_wide_event_fields, set_wide_event_nested

@router.post("/api/steps/{step_id}/submit")
async def submit_step(step_id: str, user_id: UserId, db: DbSession):
    # Add business context to wide event
    set_wide_event_fields(
        step_id=step_id,
        submission_type="code",
    )

    # For nested data
    set_wide_event_nested("step",
        id=step_id,
        topic_id=topic.id,
        phase=topic.phase,
    )

    # ... rest of handler
```

### Wide Event Schema

Every request completion log includes:

| Field | Type | Description |
|-------|------|-------------|
| `http_method` | string | GET, POST, etc. |
| `http_path` | string | Raw request path |
| `http_route` | string | FastAPI route pattern |
| `http_client_ip` | string | Client IP address |
| `http_status_code` | int | Response status code |
| `duration_ms` | float | Request duration |
| `outcome` | string | `success`, `error`, or `exception` |
| `user_id` | string | Clerk user ID (if authenticated) |
| `trace_id` | string | OpenTelemetry trace ID |
| `span_id` | string | OpenTelemetry span ID |

## Sampling Strategy

Not all requests are logged to control costs:

| Condition | Logged? |
|-----------|---------|
| Status code >= 400 | Always |
| Duration > 1000ms | Always |
| Authenticated request | Always |
| Unhandled exception | Always |
| Successful anonymous request | No |

This ensures errors, slow requests, and user actions are always captured while reducing noise from health checks and anonymous browsing.

## Azure Log Analytics (KQL) Queries

All queries target the `traces` table where structlog JSON logs are ingested.

### Basic Queries

#### All Wide Events (Last Hour)

```kusto
traces
| where timestamp > ago(1h)
| where message == "request.completed"
| project timestamp, customDimensions
| order by timestamp desc
```

#### Parse Wide Event Fields

```kusto
traces
| where timestamp > ago(1h)
| where message == "request.completed"
| extend
    http_method = tostring(customDimensions.http_method),
    http_route = tostring(customDimensions.http_route),
    status_code = toint(customDimensions.http_status_code),
    duration_ms = todouble(customDimensions.duration_ms),
    user_id = tostring(customDimensions.user_id),
    outcome = tostring(customDimensions.outcome)
| project timestamp, http_method, http_route, status_code, duration_ms, user_id, outcome
| order by timestamp desc
```

### Error Investigation

#### All Errors (4xx and 5xx)

```kusto
traces
| where timestamp > ago(24h)
| where message == "request.completed"
| extend status_code = toint(customDimensions.http_status_code)
| where status_code >= 400
| extend
    http_method = tostring(customDimensions.http_method),
    http_route = tostring(customDimensions.http_route),
    duration_ms = todouble(customDimensions.duration_ms),
    user_id = tostring(customDimensions.user_id),
    outcome = tostring(customDimensions.outcome)
| project timestamp, http_method, http_route, status_code, user_id, outcome
| order by timestamp desc
```

#### Unhandled Exceptions

```kusto
traces
| where timestamp > ago(24h)
| where message == "request.completed"
| where tostring(customDimensions.outcome) == "exception"
| extend
    http_route = tostring(customDimensions.http_route),
    exception_type = tostring(customDimensions.exception_type),
    user_id = tostring(customDimensions.user_id),
    duration_ms = todouble(customDimensions.duration_ms)
| project timestamp, http_route, exception_type, user_id, duration_ms
| order by timestamp desc
```

#### Error Rate by Endpoint

```kusto
traces
| where timestamp > ago(24h)
| where message == "request.completed"
| extend
    http_route = tostring(customDimensions.http_route),
    status_code = toint(customDimensions.http_status_code)
| summarize
    total = count(),
    errors = countif(status_code >= 400),
    error_rate = round(100.0 * countif(status_code >= 400) / count(), 2)
    by http_route
| where total > 10
| order by error_rate desc
```

### Performance Analysis

#### Slow Requests (> 1 second)

```kusto
traces
| where timestamp > ago(24h)
| where message == "request.completed"
| extend duration_ms = todouble(customDimensions.duration_ms)
| where duration_ms > 1000
| extend
    http_method = tostring(customDimensions.http_method),
    http_route = tostring(customDimensions.http_route),
    user_id = tostring(customDimensions.user_id)
| project timestamp, http_method, http_route, duration_ms, user_id
| order by duration_ms desc
```

#### P50, P90, P99 Latency by Endpoint

```kusto
traces
| where timestamp > ago(24h)
| where message == "request.completed"
| extend
    http_route = tostring(customDimensions.http_route),
    duration_ms = todouble(customDimensions.duration_ms)
| summarize
    p50 = percentile(duration_ms, 50),
    p90 = percentile(duration_ms, 90),
    p99 = percentile(duration_ms, 99),
    count = count()
    by http_route
| where count > 10
| order by p99 desc
```

#### Latency Trend Over Time

```kusto
traces
| where timestamp > ago(24h)
| where message == "request.completed"
| extend duration_ms = todouble(customDimensions.duration_ms)
| summarize
    avg_latency = avg(duration_ms),
    p99_latency = percentile(duration_ms, 99)
    by bin(timestamp, 5m)
| render timechart
```

### User Analysis

#### Requests by User (Most Active)

```kusto
traces
| where timestamp > ago(24h)
| where message == "request.completed"
| extend user_id = tostring(customDimensions.user_id)
| where isnotempty(user_id)
| summarize request_count = count() by user_id
| order by request_count desc
| take 20
```

#### Single User's Request History

```kusto
let target_user = "user_abc123";
traces
| where timestamp > ago(7d)
| where message == "request.completed"
| where tostring(customDimensions.user_id) == target_user
| extend
    http_method = tostring(customDimensions.http_method),
    http_route = tostring(customDimensions.http_route),
    status_code = toint(customDimensions.http_status_code),
    duration_ms = todouble(customDimensions.duration_ms)
| project timestamp, http_method, http_route, status_code, duration_ms
| order by timestamp desc
```

#### Users Experiencing Errors

```kusto
traces
| where timestamp > ago(24h)
| where message == "request.completed"
| extend
    user_id = tostring(customDimensions.user_id),
    status_code = toint(customDimensions.http_status_code)
| where isnotempty(user_id) and status_code >= 400
| summarize
    error_count = count(),
    endpoints_affected = dcount(tostring(customDimensions.http_route))
    by user_id
| order by error_count desc
```

### Traffic Analysis

#### Requests Per Minute

```kusto
traces
| where timestamp > ago(1h)
| where message == "request.completed"
| summarize requests = count() by bin(timestamp, 1m)
| render timechart
```

#### Traffic by Endpoint

```kusto
traces
| where timestamp > ago(24h)
| where message == "request.completed"
| extend http_route = tostring(customDimensions.http_route)
| summarize request_count = count() by http_route
| order by request_count desc
```

#### Status Code Distribution

```kusto
traces
| where timestamp > ago(24h)
| where message == "request.completed"
| extend status_code = toint(customDimensions.http_status_code)
| summarize count = count() by status_code
| order by status_code asc
| render piechart
```

### Correlation with Traces

#### Find All Spans for a Request

```kusto
let target_trace = "abc123def456";
union traces, dependencies, requests
| where timestamp > ago(24h)
| where operation_Id == target_trace or
        tostring(customDimensions.trace_id) == target_trace
| project timestamp, itemType, name, duration, success, customDimensions
| order by timestamp asc
```

## Adding Business Context

When building new features, consider what context would help debug issues:

```python
# Good: Specific, queryable fields
set_wide_event_fields(
    step_id=step.id,
    topic_id=topic.id,
    submission_result="pass",
    ai_tokens_used=150,
)

# Avoid: Generic or unstructured data
set_wide_event_field("data", str(some_object))  # Don't do this
```

### Recommended Fields by Feature

| Feature | Suggested Fields |
|---------|-----------------|
| Step submissions | `step_id`, `topic_id`, `submission_result`, `attempt_number` |
| AI interactions | `ai_model`, `ai_tokens_used`, `ai_latency_ms` |
| Certificate generation | `certificate_id`, `phase_completed` |
| GitHub integration | `github_username`, `repo_name`, `action` |

## References

- [Wide Events / Canonical Log Lines](https://loggingsucks.com/)
- [Azure Monitor KQL Reference](https://learn.microsoft.com/en-us/azure/data-explorer/kusto/query/)
- [structlog Documentation](https://www.structlog.org/)
