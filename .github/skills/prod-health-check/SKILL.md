---
name: prod-health-check
description: Check Azure production health — app status, errors, latency, database, dependencies. Use when user says "check prod", "how's prod", "hows prod doing", "is prod up", "prod status", "health check", "any errors?", "how's the app doing?", or "check Azure".
---

# Production Health Check

10 checks. One verdict. All read-only. Uses Azure CLI.

---

## Overall Verdict Logic

Evaluated top-down, first match wins:

**🔴 Critical** — ANY of:
- Readiness probe non-200
- Any 5xx errors in 24h
- DB CPU > 80% (peak)
- Fired Sev0 or Sev1 alerts in 24h
- Container crashes on current revision

**⚠️ Warning** — ANY of:
- P95 latency > 500ms
- DB CPU 50–80% (peak) or Memory 70–85% or Storage 70–85%
- Any failed availability tests in 24h
- Non-zero unhandled exceptions in 7d
- Active connections > 80

**✅ Healthy** — none of the above

---

## Step 0: Resource Discovery

```bash
SUBSCRIPTION_ID=$(grep 'subscription_id' infra/terraform.tfvars 2>/dev/null | cut -d'"' -f2)
if [ -z "$SUBSCRIPTION_ID" ]; then
  SUBSCRIPTION_ID=$(az account show --query id -o tsv)
fi
az account set --subscription "$SUBSCRIPTION_ID"

RG="rg-ltc-dev"

CA_NAME=$(az resource list -g "$RG" --resource-type "Microsoft.App/containerApps" --query "[?contains(name,'api')].name | [0]" -o tsv)
APPI_NAME=$(az resource list -g "$RG" --resource-type "microsoft.insights/components" --query "[0].name" -o tsv)
PSQL_NAME=$(az resource list -g "$RG" --resource-type "Microsoft.DBforPostgreSQL/flexibleServers" --query "[0].name" -o tsv)
LOG_NAME=$(az resource list -g "$RG" --resource-type "microsoft.operationalinsights/workspaces" --query "[0].name" -o tsv)

if [ -z "$CA_NAME" ] || [ -z "$APPI_NAME" ] || [ -z "$PSQL_NAME" ] || [ -z "$LOG_NAME" ]; then
  echo "ERROR: Could not discover all required resources in RG=$RG" >&2
  echo "CA_NAME=$CA_NAME APPI_NAME=$APPI_NAME PSQL_NAME=$PSQL_NAME LOG_NAME=$LOG_NAME" >&2
  exit 1
fi

PSQL_RESOURCE_ID="/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RG/providers/Microsoft.DBforPostgreSQL/flexibleServers/$PSQL_NAME"
WORKSPACE_ID=$(az monitor log-analytics workspace show -g "$RG" -n "$LOG_NAME" --query customerId -o tsv)
```

---

## Step 1: Container App Status + Live Readiness Probe

```bash
az containerapp show -n $CA_NAME -g $RG \
  --query "{provisioningState:properties.provisioningState, runningStatus:properties.runningStatus, latestRevision:properties.latestRevisionName, fqdn:properties.configuration.ingress.fqdn, minReplicas:properties.template.scale.minReplicas, maxReplicas:properties.template.scale.maxReplicas}" \
  -o json

FQDN=$(az containerapp show -n $CA_NAME -g $RG --query properties.configuration.ingress.fqdn -o tsv)
curl -s --max-time 5 -o /dev/null -w "ready_status=%{http_code} response_time=%{time_total}s\n" "https://$FQDN/ready"
```

**Look for**: `provisioningState: Succeeded`, `runningStatus: Running`, replica count ≥ 1. `ready_status=200`. If 503, the app reports itself as not ready (check DB connectivity or init errors). Response time > 2s is a warning.

---

## Step 2: Availability Tests (24h)

```bash
az monitor app-insights query --app $APPI_NAME -g $RG --offset P1D --analytics-query "
availabilityResults
| where timestamp > ago(24h)
| summarize Total=count(), Failed=countif(success == false), AvgDuration=avg(duration)
" --query "tables[0].rows[0]" -o tsv
```

**Look for**: `Failed` = 0. Availability tests run every 5 minutes from multiple regions — ~288 tests/day. Any failures indicate real downtime visible to users.

---

## Step 3: Request Latency P95 (24h)

```bash
az monitor app-insights query --app $APPI_NAME -g $RG --offset P1D --analytics-query "
requests
| where timestamp > ago(24h)
| summarize p95=percentile(duration, 95)
" --query "tables[0].rows[0]" -o tsv
```

**Look for**: P95 under 500ms.

---

## Step 4: HTTP Errors (24h)

```bash
az monitor app-insights query --app $APPI_NAME -g $RG --offset P1D --analytics-query "
requests
| where timestamp > ago(24h) and toint(resultCode) >= 400
| summarize Count=count() by resultCode
| order by Count desc
| take 10
" --query "tables[0].rows" -o tsv
```

**Look for**: Zero 5xx errors. 4xx should be expected (401, 404).

---

## Step 5: Error Rate Trend (7d)

```bash
az monitor app-insights query --app $APPI_NAME -g $RG --offset P7D --analytics-query "
requests
| where timestamp > ago(7d)
| summarize Total=count(), Failed=countif(success == false) by bin(timestamp, 1d)
| extend ErrorRate=round(todouble(Failed)/todouble(Total)*100, 2)
| order by timestamp desc
" --query "tables[0].rows" -o tsv
```

**Look for**: Rising `ErrorRate` trend even if each day is below the alert threshold. Stable or decreasing = healthy.

---

## Step 6: Unhandled Exceptions (7d)

**Important**: `az monitor app-insights query` has a default server-side time range of ~1 hour. You **must** pass `--offset P7D` to access 7 days of data — the `where timestamp > ago(7d)` in KQL alone is not sufficient.

```bash
az monitor app-insights query --app $APPI_NAME -g $RG --offset P7D --analytics-query "
exceptions
| where timestamp > ago(7d)
| summarize Count=count() by type, outerMessage
| order by Count desc
| take 10
" --query "tables[0].rows" -o tsv
```

**Look for**: No recurring exceptions.

---

## Step 7: Database Metrics (24h)

```bash
# Current averages
az monitor metrics list --resource "$PSQL_RESOURCE_ID" \
  --metric "cpu_percent" "memory_percent" "storage_percent" "active_connections" \
  --interval PT1H \
  --start-time "$(date -u -v-24H '+%Y-%m-%dT%H:%M:%SZ')" \
  --end-time "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" \
  --query "value[].{metric: name.value, avg: timeseries[0].data[-1].average}" \
  -o table

# Peak values
az monitor metrics list --resource "$PSQL_RESOURCE_ID" \
  --metric "cpu_percent" "memory_percent" "storage_percent" "active_connections" \
  --interval PT1H \
  --start-time "$(date -u -v-24H '+%Y-%m-%dT%H:%M:%SZ')" \
  --end-time "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" \
  --aggregation Maximum \
  --query "value[].{metric: name.value, max: timeseries[0].data[*].maximum | max(@)}" \
  -o table
```

**Thresholds** (B_Standard_B2s — 2 vCores, 4 GB RAM):

| Metric | Healthy | Warning | Critical |
|--------|---------|---------|----------|
| CPU | < 50% | 50–80% | > 80% |
| Memory | < 70% | 70–85% | > 85% |
| Storage | < 70% | 70–85% | > 85% |
| Active connections | < 80 | 80–100 | > 100 (limit ~120) |

---

## Step 8: Dependency Health (24h)

```bash
az monitor app-insights query --app $APPI_NAME -g $RG --offset P1D --analytics-query "
dependencies
| where timestamp > ago(24h)
| summarize Count=count(), FailureCount=countif(success == false) by type, target
| order by Count desc
| take 10
" --query "tables[0].rows" -o tsv
```

**Look for**: Zero `FailureCount` on PostgreSQL. Any HTTP dependency failures (GitHub API, OpenAI).

---

## Step 9: Container Stability (24h)

```bash
CURRENT_REVISION=$(az containerapp show -n $CA_NAME -g $RG --query properties.latestRevisionName -o tsv)
az monitor log-analytics query --workspace "$WORKSPACE_ID" --analytics-query "
ContainerAppSystemLogs_CL
| where TimeGenerated > ago(24h) and RevisionName_s == '$CURRENT_REVISION'
| summarize Count=count() by Reason_s, Type_s
| order by Count desc
" -o tsv
```

**Look for**: `ContainerCrashing` or `ReplicaUnhealthy` on the current revision is concerning. Events on old revisions during iterative deploys are expected — this query filters to the current revision only.

---

## Step 10: Fired Alerts (24h)

```bash
az monitor activity-log list --resource-group $RG \
  --start-time "$(date -u -v-24H '+%Y-%m-%dT%H:%M:%SZ')" \
  --status Activated \
  --query "[?contains(operationName.value, 'microsoft.insights/metricalerts') || contains(operationName.value, 'microsoft.insights/scheduledqueryrules')].{time:eventTimestamp, operation:operationName.localizedValue}" \
  -o tsv
```

**Look for**: Any activated alerts. Cross-reference with the verdict logic — Sev0/Sev1 alerts trigger 🔴 Critical.

---

## Summary Report

Present findings in this format:

```
## Production Health Report — {date}

### Overall: ✅ Healthy / ⚠️ Warning / 🔴 Critical

**Verdict reasoning**: {1-2 sentence explanation of why this verdict was chosen, citing the specific check(s) that triggered it}

| # | Check | Status | Details |
|---|-------|--------|---------|
| 1 | App Status & Readiness | ✅/🔴 | Running, {N} replicas, ready in {X}s |
| 2 | Availability Tests | ✅/⚠️ | {N} tests, {N} failed in 24h |
| 3 | Request Latency (P95) | ✅/⚠️ | {X}ms (threshold: 500ms) |
| 4 | HTTP Errors | ✅/🔴 | {N} 4xx, {N} 5xx in 24h |
| 5 | Error Rate Trend | ✅/⚠️ | {stable/rising/falling} over 7d |
| 6 | Exceptions | ✅/⚠️ | {N} unique in 7d, top: {type} |
| 7 | Database | ✅/⚠️/🔴 | CPU {X}%, Mem {X}%, Storage {X}%, Conn {X} |
| 8 | Dependencies | ✅/⚠️ | {type}: {N} calls, {N} failures |
| 9 | Container Stability | ✅/⚠️ | Current rev: {rev}, {N} crashes |
| 10 | Fired Alerts | ✅/🔴 | {N} in 24h |

### ⚠️ Items to Watch
- {any warnings — omit section if none}

### 🔴 Action Required
- {any critical issues — omit section if none}
```

---

## Notes

- **`--offset` is required for App Insights queries**: `az monitor app-insights query` defaults to a ~1 hour server-side time range. Always pass `--offset P1D` (or `P7D`) to access the full time window. The `where timestamp > ago(...)` KQL clause filters within the window but doesn't expand it.
- **Date commands**: Step 7 uses `date -u -v-24H` (macOS). On Linux: `date -u --date='24 hours ago'`.
- **Old revision events**: Step 9 filters to the current revision only. `ContainerCrashing`/`ReplicaUnhealthy` on old revisions during iterative deploys is normal and excluded.
