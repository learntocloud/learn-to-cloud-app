# Research: What a Good Production Health Check Entails

## Industry Frameworks

Three established frameworks define what to monitor in production. They overlap and complement each other.

### Google's Four Golden Signals ([SRE Book, Ch. 6](https://sre.google/sre-book/monitoring-distributed-systems/))

| Signal | What it measures | Why it matters |
|--------|-----------------|---------------|
| **Latency** | Time to serve a request (successful vs failed) | User experience. Failed requests can be fast (instant 500) — track them separately. |
| **Traffic** | Demand on the system (requests/sec, sessions, transactions) | Baseline for "normal." Sudden drops = outage. Sudden spikes = load risk. |
| **Errors** | Rate of failed requests (5xx, explicit errors, policy violations) | Direct signal of broken functionality. |
| **Saturation** | How "full" the service is (CPU, memory, connections, disk) | Predicts future failures before they happen. |

Google's advice: *"If you can only measure four metrics of your user-facing system, focus on these four."*

### RED Method (Tom Wilkie / Weaveworks)

For **request-driven services** (APIs, web apps):

| Signal | Maps to |
|--------|---------|
| **R**ate | Traffic (requests/sec) |
| **E**rrors | Errors (failed requests) |
| **D**uration | Latency (request duration) |

RED is a subset of the Golden Signals — it drops Saturation. Good for app-layer health but misses infrastructure.

### USE Method (Brendan Gregg)

For **infrastructure resources** (CPU, memory, disk, network):

| Signal | What it measures |
|--------|-----------------|
| **U**tilization | % of resource capacity used |
| **S**aturation | Work queued because resource is full |
| **E**rrors | Error events on the resource |

USE is for the database server, container host, etc. — not the app itself.

### Combined: What a Complete Health Check Covers

```
Application layer (RED/Golden Signals):
  ├── Traffic:     Request volume — is anyone using it?
  ├── Errors:      5xx rate, exception rate, failed dependency calls
  ├── Latency:     P50, P95, P99 response times
  └── Saturation:  Connection pool usage, queue depth

Infrastructure layer (USE):
  ├── Compute:     CPU %, memory %, container restarts
  ├── Database:    CPU %, memory %, storage %, active connections, failed connections
  ├── Network:     Dependency latency, DNS resolution time
  └── Storage:     Disk usage %, I/O wait

Availability layer:
  ├── Liveness:    Is the process alive? (health endpoint returns 200)
  ├── Readiness:   Can it serve traffic? (DB reachable, init complete)
  ├── Uptime:      External synthetic checks (is the FQDN responding?)
  └── Platform:    Container events (crashes, restarts, unhealthy replicas)

Operational layer:
  ├── Alerts:      Are alerts configured and firing correctly?
  ├── Deployments: Recent deploys that may correlate with issues
  ├── Logs:        Application log output (errors, warnings)
  └── Trends:      Is anything getting worse over time?
```

---

## Health Check Endpoints vs Health Check Script

Two different things, both important:

### 1. Health Check Endpoints (in the app itself)

These are HTTP endpoints the platform probes continuously. Your app already has these:

**Current implementation** ([api/routes/health_routes.py](api/routes/health_routes.py)):

```python
# /health — liveness probe (is the process alive?)
@router.get("/health")
async def health():
    return HealthResponse(status="healthy", service="learn-to-cloud-api")

# /ready — readiness probe (can it serve traffic?)
@router.get("/ready")
async def ready(request):
    # Checks: init_done, no init_error, DB reachable
    await check_db_connection(request.app.state.engine)
    return HealthResponse(status="ready", service="learn-to-cloud-api")
```

Best practice hierarchy ([OneUptime, 2026](https://oneuptime.com/blog/post/2026-01-30-health-check-design/view)):

| Endpoint | Purpose | What to check | Who calls it |
|----------|---------|--------------|-------------|
| `/health` | Liveness | Process alive, no deadlock | Container orchestrator |
| `/ready` | Readiness | DB reachable, init complete | Load balancer |
| `/health/dependencies` | Deep check | All external dependencies individually | Monitoring/debugging |

Your `/health` and `/ready` are correct and well-implemented. You're missing `/health/dependencies` — but that's a nice-to-have, not critical.

### 2. Health Check Script (the Copilot skill)

This is the **human-initiated ad-hoc audit** — "how's prod doing?" It queries telemetry, metrics, logs, and alerts from the *outside* (Azure Monitor, App Insights, Log Analytics). It's what the `prod-health-check` skill does.

These serve different purposes:

| | Health Endpoints | Health Check Script |
|---|---|---|
| **When** | Continuous (every 10-30s) | On-demand (human asks) |
| **Scope** | Single instance self-check | Whole-system audit |
| **Signal** | "Am I healthy right now?" | "How has the system been over 24h/7d?" |
| **Action** | Platform restarts unhealthy instances | Human investigates and decides |
| **Data** | Local process state | Aggregated telemetry, metrics, logs |

---

## What the Current Skill Covers (mapped to frameworks)

| Framework Signal | Current Skill Step | Coverage |
|------------------|--------------------|----------|
| **Traffic** | Step 2: Request Volume (24h) | ✅ Total requests, P95 latency |
| **Errors** | Step 3: HTTP Errors | ✅ 4xx/5xx breakdown |
| **Errors** | Step 4: Exceptions | ✅ Exception types + messages |
| **Latency** | Step 2: P95 in request summary | ✅ But only as aggregate — no per-endpoint breakdown |
| **Saturation** (app) | — | ❌ **Missing**: Connection pool usage, queue depth |
| **Saturation** (DB) | Step 6: DB Metrics | ✅ CPU, memory, storage, connections |
| **Liveness** | Step 1: Container App Status | ✅ Provisioning state, running status |
| **Readiness** | — | ❌ **Missing**: Hit `/ready` endpoint to verify app-level readiness |
| **Uptime** | — | ⚠️ **Partially missing**: Terraform configures an availability web test, but skill doesn't check its results |
| **Container events** | Step 5: System Events | ✅ Crashes, restarts, unhealthy replicas |
| **Dependencies** | Step 7: Dependency Health | ✅ PostgreSQL call count + failures |
| **Logs** | Step 8: Console Logs | ✅ Tail recent app output |
| **Alerts** | Step 9: Fired Alerts | ✅ Activity log for fired alerts |
| **Trends** | — | ❌ **Missing**: Week-over-week comparison |
| **Deployments** | — | ❌ **Missing**: Recent deploy history / revision changes |

### What's missing (prioritized)

1. **Synthetic uptime check** — Your Terraform configures an `azurerm_application_insights_standard_web_test` for availability monitoring (line 392 of [infra/monitoring.tf](infra/monitoring.tf)). The skill should check its results:
   ```bash
   az monitor app-insights query --app $APPI_NAME -g $RG --offset P1D --analytics-query "
   availabilityResults
   | where timestamp > ago(24h)
   | summarize Total=count(), Failed=countif(success == false), AvgDuration=avg(duration)
   " --query "tables[0].rows[0]" -o tsv
   ```

2. **Hit the actual `/ready` endpoint** — The skill checks Azure's view of the container but never hits the app's own readiness probe:
   ```bash
   FQDN=$(az containerapp show -n $CA_NAME -g $RG --query properties.configuration.ingress.fqdn -o tsv)
   curl -s -o /dev/null -w "%{http_code} %{time_total}s" "https://$FQDN/ready"
   ```

3. **Recent deployments** — Container App revision history shows recent deploys that might correlate with issues:
   ```bash
   az containerapp revision list -n $CA_NAME -g $RG \
     --query "[].{name:name, active:properties.active, created:properties.createdTime, state:properties.runningState}" \
     -o table
   ```

4. **Per-endpoint latency breakdown** — The current P95 is an aggregate. A single slow endpoint can hide behind a low average:
   ```bash
   az monitor app-insights query --app $APPI_NAME -g $RG --offset P1D --analytics-query "
   requests
   | where timestamp > ago(24h)
   | summarize P95=percentile(duration, 95), Count=count() by name
   | where Count > 10
   | order by P95 desc
   | take 10
   " --query "tables[0].rows" -o tsv
   ```

5. **Error rate trend** — Is the error rate stable or getting worse?
   ```bash
   az monitor app-insights query --app $APPI_NAME -g $RG --offset P7D --analytics-query "
   requests
   | where timestamp > ago(7d)
   | summarize Total=count(), Failed=countif(success == false) by bin(timestamp, 1d)
   | extend ErrorRate=round(todouble(Failed)/todouble(Total)*100, 2)
   | order by timestamp desc
   " --query "tables[0].rows" -o tsv
   ```

---

## What the Skill Already Does Well

- **Resource discovery** (Step 0) — auto-discovers resources by type, avoids hardcoded names
- **Revision-aware triage** (Step 5) — filters container events to current revision, ignores old deploy noise
- **Structured output** — summary report with ✅/⚠️/🔴 status per category
- **Threshold tables** — explicit healthy/warning/critical thresholds for DB metrics
- **Deep investigation gated** — ReplicaUnhealthy drill-down and DB queries only run when explicitly requested
- **`--offset` fix** — all App Insights queries now include `--offset P1D`/`P7D` to avoid the silent time-range clipping bug

---

## Existing Infrastructure We Should Leverage

### Configured alerts ([infra/monitoring.tf](infra/monitoring.tf))

Your Terraform already configures 12 alerts:

| Alert | Severity | What it catches |
|-------|----------|----------------|
| `api_5xx_errors` | Sev1 | 3+ 5xx errors in 5min |
| `api_restarts` | Sev1 | Container restart count > 0 |
| `api_high_cpu` | Sev2 | CPU > 80% for 5min |
| `api_high_memory` | Sev2 | Memory > 80% for 5min |
| `api_high_latency` | Sev2 | P95 latency > 2000ms |
| `db_connection_failures` | Sev1 | Failed DB connections > 0 |
| `db_storage` | Sev2 | DB storage > 80% |
| `db_high_cpu` | Sev2 | DB CPU > 80% for 5min |
| `llm_dependency_failures` | Sev2 | LLM dependency failures ≥ 3 |
| `api_4xx_spike` | Sev3 | 4xx spike detection |
| `failure_anomalies` | Sev1 | Smart detection anomalies |
| `availability` | Sev1 | Web test failure |

These alerts are the automated version of what the health check does manually. The skill's value is providing **context** when an alert fires ("why did this happen?") and catching things alerts don't cover (like gradual degradation below alert thresholds).

### Availability web test ([infra/monitoring.tf](infra/monitoring.tf#L392))

An `azurerm_application_insights_standard_web_test` pings the app's FQDN every 5 minutes from multiple Azure regions. This is the synthetic uptime monitor the skill should surface results from.

---

## Gotchas

1. **`--offset` is required on ALL `az monitor app-insights query` calls** — Without it, you get ~1 hour of data regardless of your KQL `where timestamp` filter. This was a bug in the original skill that made CLI look like it was seeing less data than Log Analytics. They are the same data source.

2. **Availability test results may lag** — The `availabilityResults` table in App Insights can take up to 10 minutes to reflect the latest probe result. Don't panic if the most recent entry is a few minutes old.

3. **Per-endpoint latency can mislead** — Some endpoints (like `/health`) are very fast and inflate the "low P95" aggregate. Always break down by endpoint name when investigating latency.

4. **Fired alerts vs configured alerts** — The skill checks fired alerts via Activity Log, not whether alerts are configured and enabled. Both matter. A misconfigured alert (disabled, wrong threshold) is a silent failure.

5. **Console logs rotate quickly** — `az containerapp logs show --tail 20` only shows the most recent logs from the current streaming session. For historical logs, use Log Analytics `ContainerAppConsoleLogs_CL`.

---

## External References

- [Google SRE Book — Monitoring Distributed Systems](https://sre.google/sre-book/monitoring-distributed-systems/) — Four Golden Signals definition
- [The RED Method](https://www.weave.works/blog/the-red-method-key-metrics-for-microservices-architecture/) — Rate, Errors, Duration
- [The USE Method](https://www.brendangregg.com/usemethod.html) — Utilization, Saturation, Errors
- [Golden Signals vs RED vs USE comparison](https://www.groundcover.com/blog/4-golden-signals) — When to use which
- [Health Check Endpoint Design](https://oneuptime.com/blog/post/2026-01-30-health-check-design/view) — Liveness/readiness/startup probe patterns
- [Kubernetes Health Probes](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/) — Official K8s probe docs
- [SRE Metrics: Four Golden Signals (Splunk)](https://www.splunk.com/en_us/blog/learn/sre-metrics-four-golden-signals-of-monitoring.html) — MTTR, MTBF, change success rate
- [Grafana Observability Survey 2025](https://grafana.com/observability-survey/2025/) — Industry trends on observability adoption
