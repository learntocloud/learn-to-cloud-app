---
name: prod-health-check
description: Check Azure production health — app logs, errors, CPU, memory, database, scaling, and dependencies. Use when user says "check prod", "how's prod", "hows prod doing", "is prod up", "prod status", "health check", "check logs", "any errors?", "how's the app doing?", or "check Azure".
---

# Production Health Check

Run a lean health check against the Azure deployment using Azure CLI.
All checks are read-only. Reports on app status, errors, performance, database, scaling, and dependencies.

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

## Step 1: Container App Status

```bash
az containerapp show -n $CA_NAME -g $RG \
  --query "{provisioningState:properties.provisioningState, runningStatus:properties.runningStatus, latestRevision:properties.latestRevisionName, fqdn:properties.configuration.ingress.fqdn, minReplicas:properties.template.scale.minReplicas, maxReplicas:properties.template.scale.maxReplicas}" \
  -o json
```

**Look for**: `provisioningState: Succeeded`, `runningStatus: Running`, replica count ≥ 1.

---

## Step 1b: Live Readiness Probe

```bash
FQDN=$(az containerapp show -n $CA_NAME -g $RG --query properties.configuration.ingress.fqdn -o tsv)
curl -s --max-time 5 -o /dev/null -w "ready_status=%{http_code} response_time=%{time_total}s\n" "https://$FQDN/ready"
```

**Look for**: `ready_status=200`. If 503, the app reports itself as not ready (check DB connectivity or init errors). Response time > 2s is a warning.

---

## Step 1c: Availability (Synthetic Uptime Test)

```bash
az monitor app-insights query --app $APPI_NAME -g $RG --offset P1D --analytics-query "
availabilityResults
| where timestamp > ago(24h)
| summarize Total=count(), Failed=countif(success == false), AvgDuration=avg(duration)
" --query "tables[0].rows[0]" -o tsv
```

**Look for**: `Failed` = 0. Availability tests run every 5 minutes from multiple regions — ~288 tests/day. Any failures indicate real downtime visible to users.

---

## Step 2: Request Volume & Latency (24h)

```bash
az monitor app-insights query --app $APPI_NAME -g $RG --offset P1D --analytics-query "
requests
| where timestamp > ago(24h)
| summarize total=count(), failed=countif(success == false), p95=percentile(duration,95)
" --query "tables[0].rows[0]" -o tsv
```

**Look for**: `failed` near zero, P95 under 500ms, consistent volume.

---

## Step 2b: Per-Endpoint Latency (24h)

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

**Look for**: Any endpoint with P95 > 500ms deserves investigation. Exclude `/health` (always fast, skews aggregate).

---

## Step 3: HTTP Errors (24h)

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

## Step 3b: Error Rate Trend (7d)

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

## Step 4: Exceptions (7d)

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

## Step 5: Container System Events (24h)

```bash
az monitor log-analytics query --workspace "$WORKSPACE_ID" --analytics-query "
ContainerAppSystemLogs_CL
| where TimeGenerated > ago(24h)
| summarize count() by Reason_s, Type_s
| order by count_ desc
" -o tsv

# Filter to current revision only
CURRENT_REVISION=$(az containerapp show -n $CA_NAME -g $RG --query properties.latestRevisionName -o tsv)
az monitor log-analytics query --workspace "$WORKSPACE_ID" --analytics-query "
ContainerAppSystemLogs_CL
| where TimeGenerated > ago(24h) and RevisionName_s == '$CURRENT_REVISION'
| summarize Count=count() by Reason_s, Type_s
| order by Count desc
" -o tsv
```

**Look for**: `ContainerCrashing` or `ReplicaUnhealthy` on the current revision is concerning. On old revisions during iterative deploys, it's expected.

---

## Step 5b: Recent Deployments

```bash
az containerapp revision list -n $CA_NAME -g $RG \
  --query "reverse(sort_by([].{name:name, active:properties.active, created:properties.createdTime, state:properties.runningState}, &created)) | [:5]" \
  -o table
```

**Look for**: Revisions in `Failed` state, revisions created in the last few hours (recent deploys), inactive revisions with `Stopped` state (normal cleanup).

---

## Step 6: Database Metrics (24h)

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

## Step 7: Dependency Health (24h)

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

## Step 8: Console Logs

```bash
az containerapp logs show -n $CA_NAME -g $RG --type console --tail 20
```

**Look for**: Only `info` level structured logs. Healthy patterns: `analytics.refreshed`, `step.completed`, `dashboard.built`. Unhealthy: Python tracebacks, `ERROR` logs, connection errors.

---

## Step 9: Fired Alerts (24h)

```bash
az monitor activity-log list --resource-group $RG \
  --start-time "$(date -u -v-24H '+%Y-%m-%dT%H:%M:%SZ')" \
  --status Activated \
  --query "[?contains(operationName.value, 'microsoft.insights/metricalerts') || contains(operationName.value, 'microsoft.insights/scheduledqueryrules')].{time:eventTimestamp, operation:operationName.localizedValue}" \
  -o tsv
```

---

## Summary Report

Present findings in this format:

```
## Production Health Report — {date}

### Overall: ✅ Healthy / ⚠️ Warning / 🔴 Critical

| Category | Status | Details |
|----------|--------|---------|
| App Status | ✅/🔴 | Running/Down, {N} replicas, revision {rev} |
| Readiness Probe | ✅/🔴 | {status_code}, {response_time}s |
| Availability Test | ✅/⚠️ | {N} tests, {N} failed in 24h |
| Request Volume | ✅ | {N} requests/24h, P95 {X}ms |
| Slowest Endpoints | ✅/⚠️ | {endpoint}: P95 {X}ms |
| HTTP Errors | ✅/⚠️ | {N} 4xx, {N} 5xx |
| Error Rate Trend | ✅/⚠️ | {stable/rising/falling} over 7d |
| Exceptions | ✅/⚠️ | {N} in 7d |
| Container Events | ✅/⚠️ | {details} |
| Recent Deploys | ✅/⚠️ | {N} revisions in 24h, {N} failed |
| DB CPU | ✅/⚠️ | Avg {X}%, Peak {X}% |
| DB Memory | ✅/⚠️ | Avg {X}%, Peak {X}% |
| DB Storage | ✅ | {X}% used |
| DB Connections | ✅/⚠️ | Avg {X}, Peak {X} (limit: ~120) |
| Dependencies | ✅/⚠️ | {type}: {N} calls, {N} failures |
| Console Logs | ✅/⚠️ | {healthy/errors seen} |
| Fired Alerts | ✅/⚠️ | {N} in 24h |

### ⚠️ Items to Watch
- {any warnings}

### 🔴 Action Required
- {any critical issues}
```

---

## Deep Investigation (only when explicitly requested)

### Container Event Drill-Down

If `ReplicaUnhealthy` appears on the current revision, pull console logs around the event:

```bash
LAST_UNHEALTHY=$(az monitor log-analytics query --workspace "$WORKSPACE_ID" --analytics-query "
ContainerAppSystemLogs_CL
| extend reason=trim(' ', tostring(Reason_s))
| where TimeGenerated > ago(24h) and RevisionName_s == '$CURRENT_REVISION' and reason == 'ReplicaUnhealthy'
| top 1 by TimeGenerated desc
| project TimeGenerated
" --query "[0].TimeGenerated" -o tsv 2>/dev/null || true)

if [ -n "$LAST_UNHEALTHY" ]; then
  echo "ReplicaUnhealthy last seen: $LAST_UNHEALTHY"
  az monitor log-analytics query --workspace "$WORKSPACE_ID" --analytics-query "
  ContainerAppConsoleLogs_CL
  | where TimeGenerated between (datetime_add('minute', -30, todatetime('$LAST_UNHEALTHY')) .. datetime_add('minute', 30, todatetime('$LAST_UNHEALTHY')))
  | project TimeGenerated, Log_s
  | order by TimeGenerated desc
  | take 50
  " -o table
fi
```

### User & Engagement Stats (Database Query)

Only run when user asks for user counts or engagement metrics. Requires firewall rule.

```bash
MY_IP=$(curl -s ifconfig.me)
az postgres flexible-server firewall-rule create \
  --resource-group $RG --name $PSQL_NAME \
  --rule-name AllowMyIP --start-ip-address $MY_IP --end-ip-address $MY_IP 2>/dev/null || true

TOKEN=$(az account get-access-token --resource-type oss-rdbms --query accessToken -o tsv)
ADMIN_USER=$(az ad signed-in-user show --query displayName -o tsv)

az postgres flexible-server execute \
  --name $PSQL_NAME \
  --admin-user "$ADMIN_USER" --admin-password "$TOKEN" \
  --database-name learntocloud \
  --querytext "SELECT 'total_users' as metric, COUNT(*)::text as value FROM users UNION ALL SELECT 'users_with_github', COUNT(*)::text FROM users WHERE github_username IS NOT NULL UNION ALL SELECT 'users_with_submissions', COUNT(DISTINCT user_id)::text FROM submissions UNION ALL SELECT 'total_submissions', COUNT(*)::text FROM submissions;" \
  -o json
```

**Note**: Requires `rdbms-connect` extension: `az extension add --name rdbms-connect --yes`.

---

## Notes

- **`--offset` is required for App Insights queries**: `az monitor app-insights query` defaults to a ~1 hour server-side time range. Always pass `--offset P1D` (or `P7D`) to access the full time window. The `where timestamp > ago(...)` KQL clause filters within the window but doesn't expand it.
- **Date commands**: Step 6 uses `date -u -v-24H` (macOS). On Linux: `date -u --date='24 hours ago'`.
- **Old revision events**: High `ContainerCrashing`/`ReplicaUnhealthy` on old revisions during iterative deploys is normal. Only current revision warnings matter.
