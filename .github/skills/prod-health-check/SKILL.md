---
name: prod-health-check
description: Check Azure production health — app logs, errors, CPU, memory, database, scaling, and dependencies. Use when user says "check prod", "health check", "check logs", "any errors?", "how's the app doing?", or "check Azure".
---

# Production Health Check

Run a comprehensive health check against the Azure deployment using Azure CLI.
Reports on app status, errors, performance, database, scaling, and dependencies.

---

## When to Use

- User says "check prod", "health check", "check logs", "check Azure"
- User says "any errors?", "how's the app doing?", "check scaling"
- User says "check database", "check CPU", "check memory"
- After a deployment to verify everything is healthy
- Periodic health audit

---

## Prerequisites

- Azure CLI (`az`) installed and logged in
- Correct subscription set (check `infra/terraform.tfvars` for `subscription_id`)

---

## Resource Discovery

**Step 0**: Set the correct subscription and discover resource names.

```bash
# Set subscription from terraform.tfvars
SUBSCRIPTION_ID=$(grep 'subscription_id' infra/terraform.tfvars | cut -d'"' -f2)
az account set --subscription "$SUBSCRIPTION_ID"

# Resource group is always rg-ltc-{environment}
RG="rg-ltc-dev"

# Discover actual resource names (suffix is random)
az resource list --resource-group "$RG" --query "[].{name:name, type:type}" -o table
```

From the output, extract:
- **Container App**: name matching `ca-ltc-api-*`
- **App Insights**: name matching `appi-ltc-*`
- **PostgreSQL**: name matching `psql-ltc-*`
- **Log Analytics**: name matching `log-ltc-*`

Store these in variables for subsequent steps:

```bash
CA_NAME="ca-ltc-api-dev"
APPI_NAME="appi-ltc-dev-SUFFIX"
PSQL_NAME="psql-ltc-dev-SUFFIX"
LOG_NAME="log-ltc-dev-SUFFIX"
PSQL_RESOURCE_ID="/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RG/providers/Microsoft.DBforPostgreSQL/flexibleServers/$PSQL_NAME"
```

---

## Step 1: Container App Status

Check provisioning state, running status, replica count, and scaling config.

```bash
# App status
az containerapp show -n $CA_NAME -g $RG \
  --query "{provisioningState:properties.provisioningState, runningStatus:properties.runningStatus, latestRevision:properties.latestRevisionName, fqdn:properties.configuration.ingress.fqdn, minReplicas:properties.template.scale.minReplicas, maxReplicas:properties.template.scale.maxReplicas}" \
  -o json

# Current replicas
az containerapp replica list -n $CA_NAME -g $RG \
  --query "[].{name:name, createdTime:properties.createdTime, runningState:properties.runningState}" -o table
```

**What to look for**:
- `provisioningState` should be `Succeeded`
- `runningStatus` should be `Running`
- Replica count should be ≥ `minReplicas` (1)
- Max replicas is 2 (limited by B1ms PostgreSQL 35-connection limit)

---

## Step 2: Request Volume & Latency (Application Insights)

```bash
# 7-day daily summary
az monitor app-insights query --app $APPI_NAME -g $RG --analytics-query "
requests
| where timestamp > ago(7d)
| summarize TotalRequests=count(), FailedRequests=countif(success == false), AvgDuration=avg(duration), P95Duration=percentile(duration, 95), P99Duration=percentile(duration, 99) by bin(timestamp, 1d)
| order by timestamp desc
" -o json

# 24h hourly breakdown
az monitor app-insights query --app $APPI_NAME -g $RG --analytics-query "
requests
| where timestamp > ago(24h)
| summarize TotalRequests=count(), FailedRequests=countif(success == false), AvgDuration=avg(duration), P95Duration=percentile(duration, 95) by bin(timestamp, 1h)
| order by timestamp desc
" -o json
```

**What to look for**:
- `FailedRequests` should be 0 or near-zero
- P95 latency under 500ms for most endpoints
- Consistent request volume (no sudden drops = no outages)

---

## Step 3: HTTP Errors (4xx/5xx)

```bash
az monitor app-insights query --app $APPI_NAME -g $RG --analytics-query "
requests
| where timestamp > ago(7d) and toint(resultCode) >= 400
| summarize Count=count() by resultCode, name
| order by Count desc
" -o json
```

**What to look for**:
- Zero 5xx errors (server errors)
- 4xx errors should be expected (401 unauthenticated, 404 not found) — not unexpected patterns

---

## Step 4: Exceptions & Error Traces

```bash
# Exceptions
az monitor app-insights query --app $APPI_NAME -g $RG --analytics-query "
exceptions
| where timestamp > ago(7d)
| summarize Count=count() by type, outerMessage
| order by Count desc
| take 20
" -o json

# Warning/Error log traces
az monitor app-insights query --app $APPI_NAME -g $RG --analytics-query "
traces
| where timestamp > ago(24h) and severityLevel >= 3
| project timestamp, message, severityLevel, customDimensions
| order by timestamp desc
| take 20
" -o json
```

**What to look for**:
- No recurring exceptions
- No `severityLevel >= 3` (WARNING) or `>= 4` (ERROR) traces

---

## Step 5: Container System Events

```bash
WORKSPACE_ID=$(az monitor log-analytics workspace show -g $RG -n $LOG_NAME --query customerId -o tsv)

# Summary of all system events by type
az monitor log-analytics query --workspace "$WORKSPACE_ID" --analytics-query "
ContainerAppSystemLogs_CL
| where TimeGenerated > ago(7d)
| summarize count() by Reason_s, Type_s
| order by count_ desc
" -o table

# Recent warning/error events
az monitor log-analytics query --workspace "$WORKSPACE_ID" --analytics-query "
ContainerAppSystemLogs_CL
| where TimeGenerated > ago(24h) and Reason_s in ('ContainerBackOff', 'ReplicaUnhealthy', 'Error', 'Deployment Progress Deadline Exceeded. 0/1 replicas ready.')
| summarize count() by Reason_s, bin(TimeGenerated, 1h)
| order by TimeGenerated desc
" -o table
```

**What to look for**:
- `ContainerBackOff`: Persistent failure to start — check container logs for crash reason
- `ReplicaUnhealthy`: Readiness/startup probe failures — expected briefly during deployments, concerning if ongoing
- `Error` with exit code 1 or 3: Container crash — check console logs
- High counts on the **current revision** are concerning; high counts on old revisions during iterative deploys are normal

---

## Step 6: Database Metrics (PostgreSQL Flexible Server)

```bash
# Current snapshot (last hour averages and peaks over 24h)
az monitor metrics list --resource "$PSQL_RESOURCE_ID" \
  --metric "cpu_percent" "memory_percent" "storage_percent" "active_connections" \
  --interval PT1H \
  --start-time "$(date -u -v-24H '+%Y-%m-%dT%H:%M:%SZ')" \
  --end-time "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" \
  --query "value[].{metric: name.value, avg: timeseries[0].data[-1].average}" \
  -o table

# Peak values over 24h
az monitor metrics list --resource "$PSQL_RESOURCE_ID" \
  --metric "cpu_percent" "memory_percent" "storage_percent" "active_connections" \
  --interval PT1H \
  --start-time "$(date -u -v-24H '+%Y-%m-%dT%H:%M:%SZ')" \
  --end-time "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" \
  --aggregation Maximum \
  --query "value[].{metric: name.value, max: timeseries[0].data[*].maximum | max(@)}" \
  -o table

# Connection trend (hourly)
az monitor metrics list --resource "$PSQL_RESOURCE_ID" \
  --metric "active_connections" \
  --interval PT1H \
  --start-time "$(date -u -v-24H '+%Y-%m-%dT%H:%M:%SZ')" \
  --end-time "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" \
  --aggregation Average Maximum \
  --query "value[0].timeseries[0].data[?average != null].{time: timeStamp, avg: average, max: maximum}" \
  -o table

# Failed connections
az monitor metrics list --resource "$PSQL_RESOURCE_ID" \
  --metric "connections_failed" \
  --interval PT1H \
  --start-time "$(date -u -v-24H '+%Y-%m-%dT%H:%M:%SZ')" \
  --end-time "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" \
  --aggregation Total \
  --query "value[].{metric: name.value, total: timeseries[0].data[*].total | sum(@)}" \
  -o table
```

**Thresholds** (B1ms tier):
| Metric | Healthy | Warning | Critical |
|--------|---------|---------|----------|
| CPU | < 40% | 40–70% | > 70% |
| Memory | < 70% | 70–85% | > 85% |
| Storage | < 70% | 70–85% | > 85% |
| Active connections | < 25 | 25–30 | > 30 (limit ~35) |
| Failed connections | 0 | 1–5 | > 5 |

**Connection budget**: Each replica uses up to 10 connections (pool_size=5 + max_overflow=5). 2 replicas × 10 = 20. B1ms allows 35 user connections.

---

## Step 7: App CPU & Memory (Performance Counters)

```bash
az monitor app-insights query --app $APPI_NAME -g $RG --analytics-query "
performanceCounters
| where timestamp > ago(24h)
| where name in ('% Processor Time', '% Processor Time Normalized', 'Private Bytes')
| summarize avg(value), max(value) by name
" -o json
```

**What to look for**:
- `% Processor Time Normalized` under 50% average
- `Private Bytes` (memory) — container is allocated 1Gi, concerning if > 800MB

---

## Step 8: Dependency Health (DB, APIs)

```bash
az monitor app-insights query --app $APPI_NAME -g $RG --analytics-query "
dependencies
| where timestamp > ago(24h)
| summarize AvgDuration=avg(duration), P95=percentile(duration, 95), Count=count(), FailureCount=countif(success == false) by type, target
| order by Count desc
| take 10
" -o json
```

**What to look for**:
- PostgreSQL P95 latency under 100ms
- Zero `FailureCount` on database dependencies
- Any HTTP dependency failures (GitHub API, OpenAI)

---

## Step 9: Console Logs (Current Revision)

```bash
az containerapp logs show -n $CA_NAME -g $RG --type console --tail 30
```

**What to look for**:
- Only `info` level structured logs
- Healthy patterns: `analytics.refreshed`, `step.completed`, `submission.validated`, `dashboard.built`
- Unhealthy: Python tracebacks, `ERROR` level logs, connection errors

---

## Step 10: Alert Status

```bash
# Configured metric alerts
az monitor metrics alert list -g $RG \
  --query "[].{name:name, enabled:enabled, severity:severity}" -o table

# Configured scheduled query alerts
az monitor scheduled-query list -g $RG \
  --query "[].{name:name, enabled:enabled, severity:severity}" -o table 2>/dev/null || true
```

---

## Summary Report Format

After gathering all data, present a summary like this:

```
## 🏥 Production Health Report — {date}

### Overall: ✅ Healthy / ⚠️ Warning / 🔴 Critical

| Category | Status | Details |
|----------|--------|---------|
| App Status | ✅ | Running, 1 replica, revision {rev} |
| Errors (4xx/5xx) | ✅ | 0 errors in 7d |
| Exceptions | ✅ | 0 exceptions in 7d |
| Request Volume | ✅ | {N} requests/day, P95 {X}ms |
| DB CPU | ✅/⚠️ | Avg {X}%, Peak {X}% |
| DB Memory | ✅/⚠️ | Avg {X}%, Peak {X}% |
| DB Storage | ✅ | {X}% used |
| DB Connections | ✅/⚠️ | Avg {X}, Peak {X} (limit: 35) |
| Failed DB Connections | ✅ | {N} in 24h |
| Container Events | ✅/⚠️ | {details about BackOff/Unhealthy if any} |
| Dependencies | ✅ | DB P95: {X}ms, 0 failures |
| Alerts | ✅ | All {N} alerts enabled, none fired |

### ⚠️ Items to Watch
- {any warnings or notes}

### 🔴 Action Required
- {any critical issues}
```

---

## Notes

- **macOS date flag**: Use `-v-24H` for 24h ago. On Linux, use `--date='24 hours ago'`.
- **Subscription**: Always verify you're on the correct subscription before running queries.
- **Timeframes**: Default to 24h for operational metrics, 7d for error/event trends.
- **BackOff events on old revisions**: During development with many iterative deploys, high BackOff counts on old/failed revisions are expected and not a production concern. Only worry if they're on the **current active revision**.
