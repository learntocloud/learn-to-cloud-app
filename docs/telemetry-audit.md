# Telemetry Audit — April 2026

Production logs, metrics, and traces reviewed against codebase. Queries ran against `log-ltc-dev-8v4tyz` workspace covering 7 days of data.

---

## What's Working

| Signal | Evidence |
|---|---|
| Structured logging (no f-strings) | 4,000+ traces use `extra={}` dicts — zero violations |
| Trace-to-request correlation | `OperationId` present on all `AppTraces` records |
| SQL dependency tracking | 5,885 tracked queries/24h via `SQLAlchemyInstrumentor` with full query text |
| Custom domain metrics | `step.completed` (225), `verification.attempt` (27), `verification.duration` (27) all flowing |
| GenAI SDK metrics | `gen_ai.client.token.usage` and `gen_ai.client.operation.duration` appearing |
| Log sanitization | CWE-117 filter stripping control chars from user fields |
| User context in log records | `user_id`, `github_username`, `topic_id`, `step_id` in Properties on all relevant trace events |

---

## Issues

### 1. `enduser.id` not reaching AppRequests

**Severity**: High
**Files**: `api/core/middleware.py` (UserTrackingMiddleware), `api/core/observability.py`

`UserTrackingMiddleware` sets `enduser.id` and `enduser.name` on the active OTel span. However, **zero out of 18,000+ `AppRequests` records contain these attributes**:

```
enduser: ""  enduser_name: ""  (every single request in the last 24h)
```

**Root cause**: FastAPI auto-instrumentation (via `FastAPIInstrumentor.instrument_app()`) creates the server span at the ASGI transport level — before any Starlette middleware runs. By the time `UserTrackingMiddleware.__call__` executes, the span has already been started and its initial attributes snapshot has been taken. Azure Monitor's exporter captures the span attributes at creation time for the `AppRequests` table, so the later `set_attribute()` calls are lost.

The logging context var path (`request_github_username`) works correctly because the `_RequestContextFilter` reads it at log-emit time (lazy), not at span-creation time.

**Impact**:
- Cannot filter or facet `AppRequests` by user in Application Insights
- Application Map and Live Metrics have no user dimension
- End-to-end transaction search cannot segment by user
- The `enduser.id` attribute set in middleware is silently discarded

**Fix**: Add a custom `SpanProcessor` that reads the session context var in `on_end()` and stamps the attributes before the span is exported. This runs after the request completes (when session data is available) but before the exporter batches the span.

---

### 2. OpenAI/LLM dependency tracked as `"chat unknown"`

**Severity**: High
**Files**: `api/core/observability.py`, `api/core/llm_client.py`

Only 1 LLM dependency call visible in 7 days of `AppDependencies`:

```
Type: AppDependencies | Target: "chat unknown" | Name: "chat unknown" | Duration: 57,885ms
```

**Root cause**: The httpx instrumentor is only configured in the OTLP code path (`_configure_otlp()`), not in the Azure Monitor code path (`_configure_azure_monitor()`). In production, `APPLICATIONINSIGHTS_CONNECTION_STRING` is set, so `_configure_azure_monitor()` runs — and it never calls `HTTPXClientInstrumentor().instrument()`. The `agent_framework` uses httpx under the hood, so LLM HTTP calls go untracked as proper dependencies.

The `"chat unknown"` entry comes from the agent framework's own internal instrumentation (enabled by `_enable_agent_framework_instrumentation()`), which creates gen_ai spans but doesn't set HTTP dependency metadata like target host or URL.

**Impact**:
- Cannot track LLM latency, error rates, or throughput per endpoint
- Application Map shows a mystery `"chat unknown"` node instead of the Azure OpenAI resource
- No alerting possible on LLM dependency failures

**Fix**: Move the httpx instrumentor call into `_configure_azure_monitor()` as well, or extract it into a shared function called by both paths.

---

### 3. GenAI tracing disabled — noisy repeated warnings

**Severity**: Medium
**Files**: Container App environment configuration

Every container restart (3 in last 7 days) and every LLM-using verification emits:

```
GenAI tracing is not enabled. Set environment variable AZURE_EXPERIMENTAL_ENABLE_GENAI_TRACING=true to enable this experimental feature.
```

10+ occurrences across 7 days at SeverityLevel 2 (Warning).

**Root cause**: The Azure OpenAI SDK checks for this env var to decide whether to emit detailed GenAI spans (prompt/completion content). Without it, only basic metrics flow.

**Impact**:
- Log noise in warning-level traces
- Missing detailed GenAI span data (prompt tokens, completion content, model parameters) that would help debug slow or failed LLM calls

**Fix**: Either:
- Set `AZURE_EXPERIMENTAL_ENABLE_GENAI_TRACING=true` in Container App env to get full GenAI tracing
- Or suppress the specific Azure SDK logger to reduce noise: `logging.getLogger("azure.ai.inference").setLevel(logging.ERROR)`

---

### 4. Zero ERROR-level logs despite 97 exceptions

**Severity**: Medium
**Files**: `api/routes/auth_routes.py`, `api/core/logger.py`

Over 7 days:
- SeverityLevel 1 (Info): **3,952** records in `AppTraces`
- SeverityLevel 2 (Warning): **84** records in `AppTraces`
- SeverityLevel 3+ (Error): **0** records in `AppTraces`

Yet `AppExceptions` contains **97 entries**: 66 `MismatchingStateError`, 26 `OAuthError`, 3 `ServiceResponseTimeoutError`, 1 `httpx.ConnectTimeout`, 1 `ConnectTimeout`.

**Root cause**: The auth callback catches OAuth exceptions and logs them with `logger.exception()`, but then re-raises the exception. Azure Monitor's exception handler captures it into `AppExceptions` — however the `logger.exception()` call may not be reaching the OTel logging bridge because the exception propagates up through Starlette's exception handling before the BatchLogRecordProcessor flushes. Alternatively, Azure Monitor may be mapping `logger.exception()` severity differently than expected.

**Impact**:
- Alerting on `AppTraces | where SeverityLevel >= 3` will never fire
- Error dashboards based on trace severity show zero errors despite real failures
- Must query `AppExceptions` separately, fragmenting the error story

**Investigation needed**: Check auth_routes.py exception handling to verify `logger.exception()` is called before the exception propagates.

---

### 5. Telemetry items being dropped

**Severity**: Low
**Files**: Azure Monitor SDK / infrastructure

`Item_Dropped_Count` over 7 days:

| Date | Count | Type | Reason |
|---|---|---|---|
| Apr 2 | 14 | CUSTOM_METRIC | CLIENT_EXCEPTION |
| Apr 3 | 1 | TRACE | CLIENT_EXCEPTION |
| Apr 6 | 1 | CUSTOM_METRIC | CLIENT_EXCEPTION |
| Apr 6 | 2 | REQUEST | CLIENT_EXCEPTION |

Plus a `ServiceResponseTimeoutError` where export to `centralus-2.in.applicationinsights.azure.com` timed out at 300s.

**Root cause**: Intermittent Azure Monitor ingestion failures. The SDK's batch exporter encounters network issues and drops items it can't retry.

**Impact**: Minimal — 18 items lost out of tens of thousands. But the `ServiceResponseTimeoutError` (300s timeout) suggests the exporter may block a thread pool thread during these failures.

**Fix**: Monitor `Item_Dropped_Count` trend. If it increases, consider tuning `BatchSpanProcessor` timeout or switching to a regional endpoint closer to the Container App.

---

### 6. Missing counters for key business events

**Severity**: Low
**Files**: `api/core/metrics.py`, `api/services/submissions_service.py`, `api/services/users_service.py`, `api/routes/auth_routes.py`

These events are **logged** (appear in `AppTraces`) but have **no OTel counter**, so they can't be used in metric-based alerts or dashboards:

| Event | Where logged | Current state |
|---|---|---|
| User account deletion | `users_service.py` | Logged only |
| Daily submission limit exceeded | `submissions_service.py` | Logged + exception raised |
| Submission cooldown enforced | `submissions_service.py` | Logged + exception raised |
| OAuth login failure | `auth_routes.py` | Logged + exception (in AppExceptions) |
| OAuth login success | `auth_routes.py` | Logged as `auth.login.success` |

**Impact**: Can't create metric-based alerts (faster than log-based) for auth failure spikes, rate limiting pressure, or churn events.

**Fix**: Add counters in `core/metrics.py` and record them at the existing log call sites.

---

### 7. `STEP_UNCOMPLETED_COUNTER` missing `phase_id` attribute

**Severity**: Low
**Files**: `api/services/steps_service.py`

`STEP_COMPLETED_COUNTER.add(1, {"phase_id": str(phase_id)})` includes `phase_id`, but need to verify `STEP_UNCOMPLETED_COUNTER` gets the same treatment.

**Impact**: Can't slice undo/uncomplete actions by phase in dashboards.

**Fix**: Verify and add `phase_id` attribute if missing.
