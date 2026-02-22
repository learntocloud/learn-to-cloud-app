# Production Health Check Research

Research into what a proper production health check should look like, how the current skills compare to industry best practices, and what changes are needed to bring both skills into parity.

---

## How the Current System Works

### Application Health Endpoints

The app exposes two health endpoints in [api/routes/health_routes.py](api/routes/health_routes.py):

**`GET /health`** (liveness probe — L18-20):
```python
@router.get("/health", response_model=HealthResponse)
async def health_check():
    return {"status": "healthy", "service": "learn-to-cloud-api"}
```
Always returns 200. No dependency checks. Pure liveness signal: "is the HTTP server responding?"

**`GET /ready`** (readiness probe — L23-68):
- Three-stage gate:
  1. **Init error check**: If `app.state.init_error` is set → 503 `"Initialization failed: {error}"`
  2. **Init completion check**: If `app.state.init_done is False` → 503 `"Starting"`
  3. **DB connectivity check**: Runs `SELECT 1` with 30s timeout → 503 `"Database unavailable"` on failure
- On success: `{"status": "ready", "service": "learn-to-cloud-api"}`
- Rate-limited: `30/minute`

### Infrastructure Probes (container-apps.tf L142-168)

**All three probes hit `/health`, not `/ready`:**

| Probe | Path | Initial Delay | Interval | Timeout | Failure Threshold |
|-------|------|---------------|----------|---------|-------------------|
| Liveness | `/health` | 30s | 30s | 5s | 3 |
| Readiness | `/health` | — | 10s | 5s | 3 |
| Startup | `/health` | — | 10s | 5s | 30 (5min window) |

**Finding**: The readiness probe in infrastructure does NOT use `/ready`. It only checks "is HTTP responding?" — it does not verify DB connectivity, init state, or dependency health. The `/ready` endpoint exists but is only used by the health check skills (via curl), not by the container orchestrator.

### Observability Stack (core/observability.py)

- **Azure Monitor**: Uses `configure_azure_monitor()` with OpenTelemetry — auto-instruments FastAPI requests, SQLAlchemy queries, HTTP clients
- **Custom metrics** (core/metrics.py): `step.completed`, `step.uncompleted`, `verification.attempt`, `verification.duration`
- **No request-level middleware metrics**: Request duration/count is handled entirely by OTel auto-instrumentation (FastAPIInstrumentor), not custom middleware

### Database (core/database.py)

| Setting | Default |
|---------|---------|
| `pool_size` | 5 |
| `max_overflow` | 5 |
| `pool_timeout` | 30s |
| `pool_recycle` | 300s |
| `pool_pre_ping` | False (asyncpg conflict) |
| Statement timeout | 10000ms |

Available but unexposed functions:
- `get_pool_status(engine)` → returns `PoolStatus(pool_size, checked_out, overflow, checked_in)`
- `check_azure_token_acquisition()` → verifies managed identity token

### Alerts (infra/monitoring.tf)

10 alert rules covering:
- 5xx errors (Sev1, ≥3 in 5min)
- Container restarts (Sev1, >2 in 5min)
- High CPU (Sev2, >80% of 0.5 CPU over 15min)
- High memory (Sev2, >80% of 1Gi over 15min)
- P95 latency (Sev2, >3s over 5min)
- DB connection failures (Sev1, >5 in 5min)
- DB storage (Sev2, >80% over 1h)
- DB CPU (Sev2, >80% over 15min)
- LLM dependency failures (Sev1, ≥5 OpenAI failures in 5min)
- 4xx auth spike (Sev2, ≥20 401/403 in 5min)

Plus: Failure Anomalies smart detector, availability test (every 5min from 3 regions), init/migration failure alert.

### Container Scaling (container-apps.tf L82-85)

- Min replicas: 1, Max replicas: 2
- Default HTTP scaling: 10 concurrent requests per replica
- Design note: 2 replicas × 10 connections (pool_size + max_overflow) = 20 DB connections

---

## Industry Best Practices

### Microsoft Azure Well-Architected Framework (RE:10)

Source: [Monitoring and Alerting Strategy](https://learn.microsoft.com/en-us/azure/well-architected/reliability/monitoring-alerting-strategy)

Key principles:
1. **Health model with states**: Define healthy, degraded, unhealthy states — alert on transitions
2. **White-box monitoring**: Instrument the app with semantic logs and metrics (what it knows internally)
3. **Black-box monitoring**: Test externally visible behavior without knowledge of internals (what users see)
4. **Health probes from multiple geo-locations**: Test from locations close to customers
5. **Structured logging**: Optimize for querying
6. **Threshold configuration as continuous improvement**: Thresholds evolve with the workload
7. **Database monitoring**: Query duration, timeouts, wait times, memory pressure, locks

### Azure Health Endpoint Monitoring Pattern

Source: [Health Endpoint Monitoring Pattern](https://learn.microsoft.com/en-us/azure/architecture/patterns/health-endpoint-monitoring)

Key checks a health endpoint should perform:
1. Availability and response time of storage/database
2. Status of other resources or services (internal and external)
3. Response code validation (200 = success)
4. Response content validation (detect partial failures)
5. Response time measurement (including network latency)
6. TLS certificate expiration
7. DNS resolution validation

Key considerations:
- **Don't overload**: Excessive processing during checks can overload the app
- **Cache endpoint status**: Periodically check, cache results, expose cached status
- **Separate liveness from readiness**: Liveness = "is this process alive?"; Readiness = "can this process handle traffic?"
- **Security**: Don't expose sensitive info through health endpoints

### Azure Container Apps Health Probes

Source: [Health probes in Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/health-probes)

Three probe types with distinct purposes:

| Probe | Purpose | What should happen on failure |
|-------|---------|------------------------------|
| **Startup** | Is the app initialized? | Wait for startup to complete (long timeout) |
| **Liveness** | Is the app hung/deadlocked? | Restart the container |
| **Readiness** | Can this replica accept traffic? | Stop routing traffic to this replica |

Best practices per Azure docs:
- **Liveness**: Lightweight — just "is the process alive?" A failure triggers a **restart**, so don't include dependency checks (DB being down shouldn't restart your app)
- **Readiness**: Check dependencies — if DB is down, mark not-ready so traffic routes elsewhere. This is where `/ready` should be used
- **Startup**: Give enough time for init/migrations — high failure threshold (e.g., 30 × 10s = 5 min)

---

## What a Proper Production Health Check Should Cover

Based on the research above, a health check is answering one meta-question: **"Is the system working correctly for users right now, and if not, why?"**

This breaks into two layers:

### Layer 1: Real-Time Status (Is it up? Right now?)

These are point-in-time checks:

| Check | What you learn | Priority |
|-------|---------------|----------|
| **Live probe (HTTP)** | Can users reach the app right now? Response code + time | Critical |
| **Readiness probe** | Is the app ready to serve? (DB connected, init done) | Critical |
| **Availability test results** | Has it been up consistently? (synthetic monitoring) | Critical |

### Layer 2: Observability Window (How has it been doing?)

These are time-windowed queries that surface trends and issues not visible from a single probe:

| Check | What you learn | Window | Priority |
|-------|---------------|--------|----------|
| **HTTP error distribution** | Are users hitting errors? (4xx expected, 5xx bad) | 24h | High |
| **Error rate trend** | Is it getting worse? (stable vs rising) | 7d | High |
| **Request latency (P95)** | Is the app slow? Per-endpoint breakdown | 24h | High |
| **Unhandled exceptions** | App bugs surfacing repeatedly? | 7d | High |
| **Database resource utilization** | CPU, memory, storage, connections vs limits | 24h | High |
| **Dependency health** | Are external calls (DB, APIs) failing? | 24h | High |
| **Container stability** | Crashes, restarts, unhealthy replicas (current revision) | 24h | Medium |
| **Application logs** | Tracebacks, ERROR-level output, unexpected patterns | 1h | Medium |
| **Fired alerts** | Has monitoring already caught something? | 24h | Medium |

### What's NOT a health check

| Item | Why it's not a health check | Where it belongs |
|------|---------------------------|-----------------|
| Request volume | Tells you how busy the app is, not whether it's healthy (0 requests at 3am is fine) | Business dashboard |
| Recent deployments | Context for "what changed?", not a health signal | Deployment log |
| User engagement stats | Business metric, not operational health | Analytics |
| Deep investigation drill-down | Troubleshooting procedure triggered by a finding, not a routine check | Runbook / follow-up |

That said: **request volume is useful as a sanity check** — a sudden drop to 0 during business hours is a problem. The question is whether it belongs in the core health check or as supplementary context.

---

## Current Skills vs Best Practices

### What both skills get right

1. **Multi-signal approach**: Check at multiple layers (app, DB, dependencies, platform)
2. **Time-windowed analysis**: Look at 24h and 7d windows, not just point-in-time
3. **Threshold definitions**: DB metrics have clear healthy/warning/critical bands
4. **Trend detection**: Error rate trend over 7d catches gradual degradation
5. **Structured report**: Consistent table format with status indicators

### Gaps and issues

#### 1. No overall health model (both skills)
The skills check individual signals but don't define what combination of signals = healthy vs degraded vs critical. Example: Is 1 failed availability test in 24h a warning? Is P95 > 500ms critical if it's only one endpoint?

**Recommendation**: Add explicit decision criteria at the top of the report logic:
- **Healthy**: All probes 200, 0 failed availability tests, 0 5xx errors, P95 < 500ms, DB < 50% CPU, no fired alerts
- **Warning**: Any of: P95 > 500ms on 1+ endpoint, DB CPU 50-80%, any failed availability tests, non-zero exceptions
- **Critical**: Any of: probe non-200, 5xx errors > 0, DB CPU > 80%, fired Sev0/1 alerts, container crashes on current revision

#### 2. Request volume is not a health signal (both skills)
Both skills include "Request Volume & Latency" as a combined step. Latency is health; volume is context. They should be separated.

**Recommendation**: Keep latency as a core check. Move volume to supplementary context or drop it.

#### 3. Recent deployments is not a health check (both skills)
Step 5b in both skills checks recent deploys. This is useful context when something is wrong ("was there a deploy?"), but isn't a health signal itself.

**Recommendation**: Move to the Deep Investigation section as context for troubleshooting.

#### 4. Per-endpoint latency is granular detail, not top-level health (both skills)
Step 2b drills into per-endpoint P95. The aggregate P95 (Step 2) is the health signal. Per-endpoint is investigation.

**Recommendation**: Keep aggregate P95 as core check. Move per-endpoint to Deep Investigation.

#### 5. Console logs overlap with exceptions (both skills)
Step 8 (console logs) checks for tracebacks and ERROR output. Step 4 (exceptions) already catches application exceptions from App Insights. These are overlapping signals — console logs add value only if exceptions aren't being captured by OTel (e.g., during startup, before instrumentation is initialized).

**Recommendation**: Keep console logs but note it's primarily for catching startup errors or issues that don't reach App Insights.

#### 6. No TLS/certificate check (both skills)
Azure Well-Architected Framework recommends checking TLS certificate expiration. Container Apps manages TLS automatically (managed cert), so this is low-risk but worth noting.

**Recommendation**: Skip — Container Apps auto-renews managed certs. Not actionable.

---

## Proposed Check Taxonomy

Based on the research, here's how the health check should be structured:

### Core Health Checks (always run)

| # | Check | Question answered | Current step |
|---|-------|-------------------|-------------|
| 1 | **Live readiness probe** | Is the app responding and ready right now? | Step 1b |
| 2 | **Availability test results** (24h) | Has it been consistently available? | Step 1c |
| 3 | **HTTP errors** (24h) | Are users hitting server errors? | Step 3 |
| 4 | **Error rate trend** (7d) | Is reliability improving or degrading? | Step 3b |
| 5 | **Request latency P95** (24h) | Is the app fast enough? | Step 2 |
| 6 | **Unhandled exceptions** (7d) | Are application bugs recurring? | Step 4 |
| 7 | **Database utilization** (24h) | Is the DB healthy? (CPU, memory, storage, connections) | Step 6 |
| 8 | **Dependency health** (24h) | Are external calls succeeding? | Step 7 |
| 9 | **Container stability** (24h) | Is the current revision stable? (crashes, restarts) | Step 5 |
| 10 | **Fired alerts** (24h) | Has monitoring already caught something? | Step 9 |

### Supplementary Context (include in report but not scored)

| # | Check | Why it's context not health |
|---|-------|-----------------------------|
| 11 | **Application logs** (1h) | Catches startup issues missed by OTel; overlaps with exceptions |
| 12 | **Request volume** (24h) | Sanity check — 0 requests during peak hours is suspicious |

### Deep Investigation (only when explicitly requested)

| # | Check |
|---|-------|
| 13 | Per-endpoint latency breakdown |
| 14 | Recent deployments / revision history |
| 15 | Container event drill-down (console logs around crashes) |
| 16 | User & engagement stats (DB query) |

---

## Parity Analysis: CLI vs MCP

### What achieves identical outcomes

| Check | CLI method | MCP method | Outcome identical? |
|-------|-----------|-----------|-------------------|
| Readiness probe | `curl /ready` | `curl /ready` | ✅ Yes |
| Availability tests | App Insights query (`availabilityResults`) | Log Analytics query (`AppAvailabilityResults`) | ✅ Yes (same data, different table name) |
| HTTP errors | App Insights query (`requests`) | Log Analytics query (`AppRequests`) | ✅ Yes |
| Error rate trend | App Insights query | Log Analytics query | ✅ Yes |
| Request latency | App Insights query | Log Analytics query | ✅ Yes |
| Exceptions | App Insights query (`exceptions`) | Log Analytics query (`AppExceptions`) | ✅ Yes |
| DB metrics | `az monitor metrics list` | `monitor_metrics_query` | ✅ Yes |
| Dependencies | App Insights query (`dependencies`) | Log Analytics query (`AppDependencies`) | ✅ Yes |
| Container events | Log Analytics query | Log Analytics query | ✅ Yes |
| Fired alerts | `az monitor activity-log list` (all alerts at once) | `monitor_activitylog_list` (per alert resource) | ✅ Yes (data identical, MCP needs iteration) |
| Console logs | `az containerapp logs show` (live stream) | Log Analytics query (`ContainerAppConsoleLogs_CL`) | ⚠️ Near-identical (1-5 min ingestion delay on MCP) |
| App status | `az containerapp show` (provisioning state, replicas, FQDN, scaling) | `resourcehealth_availability-status_list` (binary available/unavailable) | ❌ Different depth |

### What cannot achieve parity

**Container App detailed status** (CLI Step 1): The CLI gets provisioning state, running status, replica count, min/max scaling, latest revision name, and FQDN. The MCP `resourcehealth` tool only returns available/unavailable.

However: the discovery step (Step 0) in the MCP skill already runs CLI to get FQDN and container app name. We could extend discovery to also fetch these details, since discovery is already a CLI step.

**Recommendation**: In the MCP skill's Step 0 discovery, also run `az containerapp show` to capture provisioning state, replica count, and scaling config. Then reference those discovered values in Step 1 reporting. This achieves full parity since both skills already use CLI for discovery.

---

## Potential Gotchas

1. **App Insights `--offset` trap**: CLI's `az monitor app-insights query` defaults to ~1h server-side window. Without `--offset P1D` or `--offset P7D`, you get empty results for 24h/7d queries. The MCP skill avoids this because it queries Log Analytics directly (the `hours` parameter controls the window).

2. **macOS `date` vs Linux `date`**: Step 6 CLI uses `date -u -v-24H` which is macOS-only. Linux needs `date -u --date='24 hours ago'`. Both skills are used from macOS, but worth noting.

3. **Rate limit on `/ready`**: The readiness endpoint has a `30/minute` rate limit. The skills' curl probe runs once, well under the limit. But if multiple automated systems call it (skills + external uptime monitors), they share the limit per-replica (since rate limiter uses `memory://` storage, limits aren't shared across replicas).

4. **Old revision noise**: Container events for old revisions during iterative deploys produce `ContainerCrashing`/`ReplicaUnhealthy` events that look alarming but are expected. Both skills already filter to current revision — good.

5. **DB pool status is available but unused**: `get_pool_status()` exists in database.py and returns checkout/overflow info. Neither the health endpoint nor the skills check it. For a health check skill, this would need a new endpoint or DB query, which is beyond the scope of a read-only check.

---

## External References

- [Azure Health Endpoint Monitoring Pattern](https://learn.microsoft.com/en-us/azure/architecture/patterns/health-endpoint-monitoring) — The canonical pattern this app follows
- [Azure Well-Architected Framework RE:10 – Monitoring and Alerting Strategy](https://learn.microsoft.com/en-us/azure/well-architected/reliability/monitoring-alerting-strategy) — Health model, white-box/black-box monitoring
- [Azure Container Apps Health Probes](https://learn.microsoft.com/en-us/azure/container-apps/health-probes) — Startup/liveness/readiness probe specs and defaults
- [Azure Monitor Baseline Alerts (AMBA)](https://learn.microsoft.com/en-us/azure/azure-monitor/alerts/alert-options#azure-monitor-baseline-alerts-amba) — Community baseline for alert definitions

---

## Summary

The current skills cover the right signals. The main opportunity is **structural** — reorganizing checks into core health (10 checks that directly answer "is it healthy?"), supplementary context (2 items that provide useful framing), and deep investigation (4 items for troubleshooting). Both skills should implement the same 10 core checks + 2 context items in the main flow, with deep investigation as a separate section.

The MCP skill can achieve full parity with CLI by extending its Step 0 discovery to also capture container app status details (provisioning state, replicas, scaling) since it already runs CLI there.
