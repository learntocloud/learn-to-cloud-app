---
name: prod-health-check
description: Check Azure production health — app logs, errors, CPU, memory, database, scaling, and dependencies. Use when user says "check prod", "how's prod", "hows prod doing", "is prod up", "prod status", "health check", "check logs", "any errors?", "how's the app doing?", or "check Azure".
---

# Production Health Check

Run a comprehensive health check against the Azure deployment using Azure CLI.
Reports on app status, errors, performance, database, scaling, and dependencies.

Use a phased workflow aligned with Copilot agent loops:
1. **Research** (read-only checks, no changes)
2. **Plan** (summarize findings and risks)
3. **Execute** (only if user asks for deeper checks or remediation)
4. **Validate** (re-check impacted signals)
5. **Report** (status + action items)

---

## When to Use

- User says "check prod", "health check", "check logs", "check Azure"
- User says "any errors?", "how's the app doing?", "check scaling"
- User says "check database", "check CPU", "check memory"
- After a deployment to verify everything is healthy
- Periodic health audit

---

## Research vs Code Modes (Important)

When this skill is invoked, choose the lightest mode that satisfies the request.

### Mode A — Research-Only (default)

Use for prompts like:
- "how's our app doing"
- "any errors?"
- "quick health check"

Behavior:
- Run read-only checks first (Steps 0-10)
- Skip firewall changes and DB query unless user explicitly asks for user counts/engagement
- Return concise status with risk callouts

### Mode B — Code/Execution (deeper investigation or remediation)

Use for prompts like:
- "investigate and fix"
- "why did alerts fire"
- "resolve unhealthy replicas"

Behavior:
- Start with Mode A
- Then run deeper checks (Step 11, targeted logs, revision-level analysis)
- Only perform mutating actions (restart/redeploy/firewall changes) when explicitly requested

---

## Prerequisites

- Azure CLI (`az`) installed and logged in
- Correct subscription set (check `infra/terraform.tfvars` for `subscription_id`)
- Azure CLI extension `rdbms-connect` (for DB queries): `az extension add --name rdbms-connect --yes`

---

## Resource Discovery

**Step 0**: Set the correct subscription and discover resource names.

Prefer auto-discovery to avoid copy/paste mistakes when resource suffixes change.

```bash
# Set subscription — terraform.tfvars is gitignored, so fall back to az account show
SUBSCRIPTION_ID=$(grep 'subscription_id' infra/terraform.tfvars 2>/dev/null | cut -d'"' -f2)
if [ -z "$SUBSCRIPTION_ID" ]; then
  SUBSCRIPTION_ID=$(az account show --query id -o tsv)
fi
az account set --subscription "$SUBSCRIPTION_ID"

# Resource group is fixed for this project
RG="rg-ltc-dev"

# Auto-discover resource names (suffix is random)
CA_NAME=$(az resource list -g "$RG" --resource-type "Microsoft.App/containerApps" --query "[?contains(name,'api')].name | [0]" -o tsv)
APPI_NAME=$(az resource list -g "$RG" --resource-type "microsoft.insights/components" --query "[0].name" -o tsv)
PSQL_NAME=$(az resource list -g "$RG" --resource-type "Microsoft.DBforPostgreSQL/flexibleServers" --query "[0].name" -o tsv)
LOG_NAME=$(az resource list -g "$RG" --resource-type "microsoft.operationalinsights/workspaces" --query "[0].name" -o tsv)

# Fail fast if any required resource is missing (prevents confusing blank query output later)
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
- Max replicas is 2 (limited by B_Standard_B2s PostgreSQL ~120-connection limit)

---

## Step 2: Request Volume & Latency (Application Insights)

```bash
# Tip: `az monitor app-insights query` can render blank with `-o table`. Prefer `-o json`
# or extract rows directly: `--query 'tables[0].rows' -o tsv`.

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

# Quick single-row summary (24h): total / failed / p95
az monitor app-insights query --app $APPI_NAME -g $RG --analytics-query "
requests
| where timestamp > ago(24h)
| summarize total=count(), failed=countif(success == false), p95=percentile(duration,95)
" --query "tables[0].rows[0]" -o tsv
```

If your tenant rejects duration conversion expressions, use this fallback (reliability first, latency second):

```bash
az monitor app-insights query --app $APPI_NAME -g $RG --analytics-query "
requests
| where timestamp > ago(24h)
| summarize TotalRequests=count(), FailedRequests=countif(success == false)
" -o json

az monitor app-insights query --app $APPI_NAME -g $RG --analytics-query "
requests
| where timestamp > ago(24h)
| summarize AvgDuration=avg(duration), P95Duration=percentile(duration,95), P99Duration=percentile(duration,99)
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

# Quick view (24h): status code counts only
az monitor app-insights query --app $APPI_NAME -g $RG --analytics-query "
requests
| where timestamp > ago(24h) and toint(resultCode) >= 400
| summarize Count=count() by resultCode
| order by Count desc
| take 10
" --query "tables[0].rows" -o tsv

# 24h breakdown of common 404/405 noise (favicon/robots/scanners/etc.)
az monitor app-insights query --app $APPI_NAME -g $RG --analytics-query "
requests
| where timestamp > ago(24h) and toint(resultCode) in (404,405)
| summarize Count=count() by resultCode, url
| order by Count desc
| take 25
" --query "tables[0].rows" -o tsv
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

# Warning+ log traces (severityLevel: 2=Warning, 3=Error, 4=Critical)
az monitor app-insights query --app $APPI_NAME -g $RG --analytics-query "
traces
| where timestamp > ago(24h) and severityLevel >= 2
| project timestamp, message, severityLevel, customDimensions
| order by timestamp desc
| take 20
" -o json
```

**What to look for**:
- No recurring exceptions
- No `severityLevel >= 2` (Warning+) traces

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

# Critical: isolate warnings on the CURRENT active revision only
CURRENT_REVISION=$(az containerapp show -n $CA_NAME -g $RG --query properties.latestRevisionName -o tsv)
az monitor log-analytics query --workspace "$WORKSPACE_ID" --analytics-query "
ContainerAppSystemLogs_CL
| where TimeGenerated > ago(24h) and RevisionName_s == '$CURRENT_REVISION'
| summarize Count=count() by Reason_s, Type_s
| order by Count desc
" -o table

# If you see `ReplicaUnhealthy` on the current revision, pull console logs around the last event time.
LAST_UNHEALTHY=$(az monitor log-analytics query --workspace "$WORKSPACE_ID" --analytics-query "
ContainerAppSystemLogs_CL
| extend reason=trim(' ', tostring(Reason_s))
| where TimeGenerated > ago(24h) and RevisionName_s == '$CURRENT_REVISION' and reason == 'ReplicaUnhealthy'
| top 1 by TimeGenerated desc
| project TimeGenerated
" --query "[0].TimeGenerated" -o tsv 2>/dev/null || true)

if [ -n "$LAST_UNHEALTHY" ]; then
  echo "ReplicaUnhealthy last seen: $LAST_UNHEALTHY"

  # Show the raw system log row(s) around the event.
  az monitor log-analytics query --workspace "$WORKSPACE_ID" --analytics-query "
  ContainerAppSystemLogs_CL
  | where RevisionName_s == '$CURRENT_REVISION'
  | where TimeGenerated between (datetime_add('minute', -30, todatetime('$LAST_UNHEALTHY')) .. datetime_add('minute', 30, todatetime('$LAST_UNHEALTHY')))
  | project TimeGenerated, Reason_s, Type_s, Message
  | order by TimeGenerated desc
  | take 20
  " -o table

  # Console logs can lag system events or not line up perfectly; use a wider window.
  az monitor log-analytics query --workspace "$WORKSPACE_ID" --analytics-query "
  ContainerAppConsoleLogs_CL
  | where TimeGenerated between (datetime_add('minute', -30, todatetime('$LAST_UNHEALTHY')) .. datetime_add('minute', 30, todatetime('$LAST_UNHEALTHY')))
  | project TimeGenerated, Log_s
  | order by TimeGenerated desc
  | take 50
  " -o table
fi
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

**Thresholds** (B_Standard_B2s tier — 2 vCores, 4 GB RAM):
| Metric | Healthy | Warning | Critical |
|--------|---------|---------|----------|
| CPU | < 50% | 50–80% | > 80% |
| Memory | < 70% | 70–85% | > 85% |
| Storage | < 70% | 70–85% | > 85% |
| Active connections | < 80 | 80–100 | > 100 (limit ~120) |
| Failed connections | 0 | 1–5 | > 5 |

**Connection budget**: Each replica uses up to 10 connections (pool_size=5 + max_overflow=5). 2 replicas × 10 = 20. B_Standard_B2s allows ~120 user connections.

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

# Filter out local/internal noise so external dependencies stand out (if present in your telemetry):
az monitor app-insights query --app $APPI_NAME -g $RG --analytics-query "
dependencies
| where timestamp > ago(24h)
| where isnotempty(target)
| where not(target has 'localhost' or target has '127.0.0.1' or target has '100.100.')
| where not(type == 'N/A' and target == 'GET')
| summarize Count=count(), FailureCount=countif(success == false) by type, target
| order by Count desc
| take 10
" --query "tables[0].rows" -o tsv
```

Fallback (if duration conversion/projection fails in your environment):

```bash
az monitor app-insights query --app $APPI_NAME -g $RG --analytics-query "
dependencies
| where timestamp > ago(24h)
| summarize Count=count(), FailureCount=countif(success == false) by type, target
| order by Count desc
| take 10
" -o json
```

**What to look for**:
- PostgreSQL P95 latency under 100ms
- Zero `FailureCount` on database dependencies
- Any HTTP dependency failures (GitHub API, OpenAI)

---

## Step 8b: Telemetry Richness (Sanity Check)

Validate that logs are structured (rich `customDimensions`), and that tracing captures
dependencies (e.g. PostgreSQL) and correlates with requests.

```bash
# Traces: volume + sample with customDimensions
az monitor app-insights query --app $APPI_NAME -g $RG --analytics-query "
traces
| where timestamp > ago(24h)
| summarize total=count()
" --query "tables[0].rows[0][0]" -o tsv

az monitor app-insights query --app $APPI_NAME -g $RG --analytics-query "
traces
| where timestamp > ago(24h)
| project timestamp, severityLevel, message, customDimensions
| order by timestamp desc
| take 10
" -o json

# Traces: which structured keys are present
az monitor app-insights query --app $APPI_NAME -g $RG --analytics-query "
traces
| where timestamp > ago(24h)
| extend k=bag_keys(customDimensions)
| mv-expand k
| summarize keys=make_set(k, 50)
" -o json

# Dependencies: ensure DB spans exist
az monitor app-insights query --app $APPI_NAME -g $RG --analytics-query "
dependencies
| where timestamp > ago(24h)
| summarize Count=count(), FailureCount=countif(success == false) by type, target
| order by Count desc
| take 10
" -o json

# Correlation: join traces <-> requests by operation_Id
az monitor app-insights query --app $APPI_NAME -g $RG --analytics-query "
let t = traces | where timestamp > ago(1h) | project operation_Id, event=message;
let r = requests | where timestamp > ago(1h) | project operation_Id, req=name, code=resultCode;
t | join kind=inner (r) on operation_Id
| project req, code, event
| take 20
" --query "tables[0].rows" -o tsv
```

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

# Fired alerts in last 24h (use Activity Log as source of truth)
az monitor activity-log list --resource-group $RG \
  --start-time "$(date -u -v-24H '+%Y-%m-%dT%H:%M:%SZ')" \
  --status Activated \
  --query "[?contains(operationName.value, 'microsoft.insights/metricalerts') || contains(operationName.value, 'microsoft.insights/scheduledqueryrules')].{time:eventTimestamp, operation:operationName.localizedValue, status:status.localizedValue, subStatus:subStatus.localizedValue}" \
  -o table
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
| DB Connections | ✅/⚠️ | Avg {X}, Peak {X} (limit: ~120) |
| Failed DB Connections | ✅ | {N} in 24h |
| Container Events | ✅/⚠️ | {details about BackOff/Unhealthy if any} |
| Dependencies | ✅ | DB P95: {X}ms, 0 failures |
| Alerts | ✅/⚠️ | All {N} alerts enabled; {N} fired in 24h |
| Users | ✅ | {N} total, {N} with submissions, {N} active 30d |

### ⚠️ Items to Watch
- {any warnings or notes}

### 🔴 Action Required
- {any critical issues}
```

---

## Step 11: User & Engagement Stats (Database Query)

Query the production database for user and engagement metrics. This answers "how many users do we have?" which is almost always part of a health check.

Run this step only when the user asks for user counts, engagement metrics, or deeper product-health context.

**Prerequisites**: Ensure your IP is allowed through the PostgreSQL firewall.

```bash
# Check/create firewall rule for your IP
MY_IP=$(curl -s ifconfig.me)
az postgres flexible-server firewall-rule create \
  --resource-group $RG --name $PSQL_NAME \
  --rule-name AllowMyIP --start-ip-address $MY_IP --end-ip-address $MY_IP 2>/dev/null || true

# Get Entra ID token
TOKEN=$(az account get-access-token --resource-type oss-rdbms --query accessToken -o tsv)
ADMIN_USER=$(az ad signed-in-user show --query displayName -o tsv)

# Query user stats (uses az postgres — no psql binary needed)
az postgres flexible-server execute \
  --name $PSQL_NAME \
  --admin-user "$ADMIN_USER" --admin-password "$TOKEN" \
  --database-name learntocloud \
  --querytext "SELECT 'total_users' as metric, COUNT(*)::text as value FROM users UNION ALL SELECT 'users_with_github', COUNT(*)::text FROM users WHERE github_username IS NOT NULL UNION ALL SELECT 'users_with_submissions', COUNT(DISTINCT user_id)::text FROM submissions UNION ALL SELECT 'total_submissions', COUNT(*)::text FROM submissions;" \
  -o json
```

**Note**: This command requires the `rdbms-connect` Azure CLI extension. Install with `az extension add --name rdbms-connect --yes`. Unlike `psql`, this works without a local PostgreSQL client installation.

**What to look for**:
- Total user count trending upward
- Ratio of users with submissions (engagement rate)

---

## Notes

- **Subscription**: `infra/terraform.tfvars` is gitignored — use `az account show --query id -o tsv` as fallback.
- **Timeframes**: Default to 24h for operational metrics, 7d for error/event trends.
- **BackOff events on old revisions**: During development with many iterative deploys, high BackOff counts on old/failed revisions are expected and not a production concern. Only worry if they're on the **current active revision**.
- **Revision-aware triage**: Treat `ReplicaUnhealthy` or `ContainerBackOff` as action-required only when repeated on the current active revision.
- **Alerts health**: "Enabled" is configuration health. Use Activity Log to confirm whether alerts actually fired recently.
- **Research-first default**: For broad status prompts, complete read-only checks first and present findings before taking any mutating action.
- **DB access**: The `az postgres flexible-server execute` command (via `rdbms-connect` extension) is preferred over `psql` since it doesn't require a local PostgreSQL client. Always ensure your IP has a firewall rule before querying.

### Cross-platform date commands

The DB metrics commands in Step 6 use `date -u -v-24H` (macOS). On Linux (CI), use `date -u --date='24 hours ago'` instead.

| OS | 24 hours ago | Now |
|---|---|---|
| **macOS** | `$(date -u -v-24H '+%Y-%m-%dT%H:%M:%SZ')` | `$(date -u '+%Y-%m-%dT%H:%M:%SZ')` |
| **Linux** | `$(date -u --date='24 hours ago' '+%Y-%m-%dT%H:%M:%SZ')` | `$(date -u '+%Y-%m-%dT%H:%M:%SZ')` |
