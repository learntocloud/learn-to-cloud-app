---
name: prod-health-check-mcp
description: Check Azure production health using Azure MCP tools only (no Azure CLI). Use when user says "check prod with mcp", "mcp health check", or "health check mcp". This is the MCP-only variant for comparison testing.
---

# Production Health Check (Azure MCP Only)

Run a health check against the Azure deployment using **Azure MCP tools** for all health checks.
Uses a one-time CLI bootstrap (Step 0) to discover resource names — MCP lacks a generic resource listing tool.
All checks are read-only.

---

## Step 0: Resource Discovery

Run this CLI block first to discover resource names. Use the discovered values in all subsequent MCP tool calls.

```bash
SUBSCRIPTION_ID=$(grep 'subscription_id' infra/terraform.tfvars 2>/dev/null | cut -d'"' -f2)
if [ -z "$SUBSCRIPTION_ID" ]; then
  SUBSCRIPTION_ID=$(az account show --query id -o tsv)
fi
az account set --subscription "$SUBSCRIPTION_ID"

RG="rg-ltc-dev"

CA_NAME=$(az resource list -g "$RG" --resource-type "Microsoft.App/containerApps" --query "[?contains(name,'api')].name | [0]" -o tsv)
LOG_NAME=$(az resource list -g "$RG" --resource-type "microsoft.operationalinsights/workspaces" --query "[0].name" -o tsv)
PSQL_NAME=$(az resource list -g "$RG" --resource-type "Microsoft.DBforPostgreSQL/flexibleServers" --query "[0].name" -o tsv)
FQDN=$(az containerapp show -n $CA_NAME -g $RG --query properties.configuration.ingress.fqdn -o tsv)
ALERT_NAMES=$(az resource list -g "$RG" --resource-type "microsoft.insights/scheduledqueryrules" --query "[].name" -o tsv)

if [ -z "$CA_NAME" ] || [ -z "$LOG_NAME" ] || [ -z "$PSQL_NAME" ]; then
  echo "ERROR: Could not discover all required resources in RG=$RG" >&2
  echo "CA_NAME=$CA_NAME LOG_NAME=$LOG_NAME PSQL_NAME=$PSQL_NAME" >&2
  exit 1
fi

echo "SUBSCRIPTION_ID=$SUBSCRIPTION_ID"
echo "RG=$RG"
echo "CA_NAME=$CA_NAME"
echo "LOG_NAME=$LOG_NAME"
echo "PSQL_NAME=$PSQL_NAME"
echo "FQDN=$FQDN"
echo "ALERT_NAMES=$ALERT_NAMES"
```

Save the discovered values. Use them as the `subscription`, `resource-group`, `workspace`, `resource`, and `resource-name` parameters in all MCP tool calls below.

---

## Step 1: Resource Health (all resources)

Use MCP tool: `resourcehealth_availability-status_list`
- subscription: `{SUBSCRIPTION_ID}`
- resource-group: `{RG}`

**Look for**: All resources showing `Available`. Any `Unavailable` or `Degraded` is a critical issue.

**Note**: This replaces the CLI's `az containerapp show` but provides less detail — no provisioning state, replica count, or revision info. It's a binary "available or not" check.

---

## Step 1b: Live Readiness Probe

Run in terminal (curl is not an MCP tool, but this is essential):
```bash
curl -s --max-time 5 -o /dev/null -w "ready_status=%{http_code} response_time=%{time_total}s\n" "https://{FQDN}/ready"
```

**Look for**: `ready_status=200`. If 503, the app reports itself as not ready.

---

## Step 1c: Availability (Synthetic Uptime Test)

Use MCP tool: `monitor_workspace_log_query`
- subscription: `{SUBSCRIPTION_ID}`
- resource-group: `{RG}`
- workspace: `{LOG_NAME}`
- table: `AppAvailabilityResults`
- query: `AppAvailabilityResults | where TimeGenerated > ago(24h) | summarize Total=count(), Failed=countif(Success == false), AvgDuration=avg(DurationMs)`
- hours: 24

**Look for**: `Failed` = 0.

---

## Step 2: Request Volume & Latency (24h)

Use MCP tool: `monitor_workspace_log_query`
- subscription: `{SUBSCRIPTION_ID}`
- resource-group: `{RG}`
- workspace: `{LOG_NAME}`
- table: `AppRequests`
- query: `AppRequests | where TimeGenerated > ago(24h) | summarize total=count(), failed=countif(Success == false), p95=percentile(DurationMs, 95)`
- hours: 24

**Look for**: `failed` near zero, P95 under 500ms.

---

## Step 2b: Per-Endpoint Latency (24h)

Use MCP tool: `monitor_workspace_log_query`
- subscription: `{SUBSCRIPTION_ID}`
- resource-group: `{RG}`
- workspace: `{LOG_NAME}`
- table: `AppRequests`
- query: `AppRequests | where TimeGenerated > ago(24h) | summarize P95=percentile(DurationMs, 95), Count=count() by OperationName | where Count > 10 | order by P95 desc | take 10`
- hours: 24

**Look for**: Any endpoint with P95 > 500ms.

---

## Step 3: HTTP Errors (24h)

Use MCP tool: `monitor_workspace_log_query`
- subscription: `{SUBSCRIPTION_ID}`
- resource-group: `{RG}`
- workspace: `{LOG_NAME}`
- table: `AppRequests`
- query: `AppRequests | where TimeGenerated > ago(24h) and toint(ResultCode) >= 400 | summarize Count=count() by ResultCode | order by Count desc | take 10`
- hours: 24

**Look for**: Zero 5xx errors. 4xx should be expected (401, 404).

---

## Step 3b: Error Rate Trend (7d)

Use MCP tool: `monitor_workspace_log_query`
- subscription: `{SUBSCRIPTION_ID}`
- resource-group: `{RG}`
- workspace: `{LOG_NAME}`
- table: `AppRequests`
- query: `AppRequests | where TimeGenerated > ago(7d) | summarize Total=count(), Failed=countif(Success == false) by bin(TimeGenerated, 1d) | extend ErrorRate=round(todouble(Failed)/todouble(Total)*100, 2) | order by TimeGenerated desc`
- hours: 168

**Look for**: Rising `ErrorRate` trend. Stable or decreasing = healthy.

---

## Step 4: Exceptions (7d)

Use MCP tool: `monitor_workspace_log_query`
- subscription: `{SUBSCRIPTION_ID}`
- resource-group: `{RG}`
- workspace: `{LOG_NAME}`
- table: `AppExceptions`
- query: `AppExceptions | where TimeGenerated > ago(7d) | summarize Count=count() by ExceptionType, OuterMessage | order by Count desc | take 10`
- hours: 168

**Look for**: No recurring exceptions.

---

## Step 5: Container System Events (24h)

First, get the overview across all revisions:

Use MCP tool: `monitor_workspace_log_query`
- subscription: `{SUBSCRIPTION_ID}`
- resource-group: `{RG}`
- workspace: `{LOG_NAME}`
- table: `ContainerAppSystemLogs_CL`
- query: `ContainerAppSystemLogs_CL | where TimeGenerated > ago(24h) | summarize count() by Reason_s, Type_s | order by count_ desc`
- hours: 24

Then filter to the latest revision only (old revision events during iterative deploys are expected noise):

Use MCP tool: `monitor_workspace_log_query`
- subscription: `{SUBSCRIPTION_ID}`
- resource-group: `{RG}`
- workspace: `{LOG_NAME}`
- table: `ContainerAppSystemLogs_CL`
- query: `ContainerAppSystemLogs_CL | where TimeGenerated > ago(24h) | summarize arg_max(TimeGenerated, RevisionName_s) by RevisionName_s | top 1 by TimeGenerated desc | project LatestRevision=RevisionName_s`
- hours: 24

Use the returned `LatestRevision` value in a follow-up query:

Use MCP tool: `monitor_workspace_log_query`
- subscription: `{SUBSCRIPTION_ID}`
- resource-group: `{RG}`
- workspace: `{LOG_NAME}`
- table: `ContainerAppSystemLogs_CL`
- query: `ContainerAppSystemLogs_CL | where TimeGenerated > ago(24h) and RevisionName_s == '{LATEST_REVISION}' | summarize Count=count() by Reason_s, Type_s | order by Count desc`
- hours: 24

**Look for**: `ContainerCrashing` or `ReplicaUnhealthy` on the latest revision is concerning. On old revisions during iterative deploys, it's expected.

---

## Step 5b: Recent Deployments

Use MCP tool: `monitor_workspace_log_query`
- subscription: `{SUBSCRIPTION_ID}`
- resource-group: `{RG}`
- workspace: `{LOG_NAME}`
- table: `ContainerAppSystemLogs_CL`
- query: `ContainerAppSystemLogs_CL | where TimeGenerated > ago(7d) | distinct RevisionName_s | order by RevisionName_s desc | take 5`
- hours: 168

**Look for**: Multiple revisions in the last 24h indicates recent deploys. Cross-reference with Step 5 to see if any revision had `ContainerCrashing` events.

---

## Step 6: Database Metrics (24h)

Get average values:

Use MCP tool: `monitor_metrics_query`
- subscription: `{SUBSCRIPTION_ID}`
- resource-group: `{RG}`
- resource: `{PSQL_NAME}`
- resource-type: `Microsoft.DBforPostgreSQL/flexibleServers`
- metric-namespace: `Microsoft.DBforPostgreSQL/flexibleServers`
- metric-names: `cpu_percent,memory_percent,storage_percent,active_connections`
- aggregation: `Average`
- interval: `PT1H`

Get peak values:

Use MCP tool: `monitor_metrics_query`
- subscription: `{SUBSCRIPTION_ID}`
- resource-group: `{RG}`
- resource: `{PSQL_NAME}`
- resource-type: `Microsoft.DBforPostgreSQL/flexibleServers`
- metric-namespace: `Microsoft.DBforPostgreSQL/flexibleServers`
- metric-names: `cpu_percent,memory_percent,storage_percent,active_connections`
- aggregation: `Maximum`
- interval: `PT1H`

**Thresholds** (B_Standard_B2s — 2 vCores, 4 GB RAM):

| Metric | Healthy | Warning | Critical |
|--------|---------|---------|----------|
| CPU | < 50% | 50–80% | > 80% |
| Memory | < 70% | 70–85% | > 85% |
| Storage | < 70% | 70–85% | > 85% |
| Active connections | < 80 | 80–100 | > 100 (limit ~120) |

---

## Step 7: Dependency Health (24h)

Use MCP tool: `monitor_workspace_log_query`
- subscription: `{SUBSCRIPTION_ID}`
- resource-group: `{RG}`
- workspace: `{LOG_NAME}`
- table: `AppDependencies`
- query: `AppDependencies | where TimeGenerated > ago(24h) | summarize Count=count(), FailureCount=countif(Success == false) by DependencyType, Target | order by Count desc | take 10`
- hours: 24

**Look for**: Zero `FailureCount` on PostgreSQL.

---

## Step 8: Console Logs

**⚠️ NOT POSSIBLE WITH MCP** — No Azure MCP tool exists for Container App console logs. This is a known gap.

Fallback: query recent traces from Log Analytics instead:

Use MCP tool: `monitor_workspace_log_query`
- subscription: `{SUBSCRIPTION_ID}`
- resource-group: `{RG}`
- workspace: `{LOG_NAME}`
- table: `ContainerAppConsoleLogs_CL`
- query: `ContainerAppConsoleLogs_CL | where TimeGenerated > ago(1h) | project TimeGenerated, Log_s | order by TimeGenerated desc | take 20`
- hours: 1

**Look for**: Only `info` level structured logs. Unhealthy: Python tracebacks, `ERROR` logs.

---

## Step 9: Fired Alerts (24h)

Use MCP tool: `monitor_activitylog_list` — call once per alert resource discovered in Step 0.
- subscription: `{SUBSCRIPTION_ID}`
- resource-group: `{RG}`
- resource-name: `{each ALERT_NAME}`
- resource-type: `microsoft.insights/scheduledqueryrules`
- hours: 24

**Note**: MCP `monitor_activitylog_list` requires a specific resource name. Iterate over all `ALERT_NAMES` discovered in Step 0.

---

## Summary Report

Present findings in this format:

```
## Production Health Report (MCP) — {date}

### Overall: ✅ Healthy / ⚠️ Warning / 🔴 Critical

| Category | Status | Details |
|----------|--------|---------|
| Resource Health | ✅/🔴 | All {N} resources Available / {N} degraded |
| Readiness Probe | ✅/🔴 | {status_code}, {response_time}s |
| Availability Test | ✅/⚠️ | {N} tests, {N} failed in 24h |
| Request Volume | ✅ | {N} requests/24h, P95 {X}ms |
| Slowest Endpoints | ✅/⚠️ | {endpoint}: P95 {X}ms |
| HTTP Errors | ✅/⚠️ | {N} 4xx, {N} 5xx |
| Error Rate Trend | ✅/⚠️ | {stable/rising/falling} over 7d |
| Exceptions | ✅/⚠️ | {N} in 7d |
| Container Events | ✅/⚠️ | {details} |
| Recent Deploys | ✅/⚠️ | {N} revisions in 7d |
| DB CPU | ✅/⚠️ | Avg {X}%, Peak {X}% |
| DB Memory | ✅/⚠️ | Avg {X}%, Peak {X}% |
| DB Storage | ✅ | {X}% used |
| DB Connections | ✅/⚠️ | Avg {X}, Peak {X} (limit: ~120) |
| Dependencies | ✅/⚠️ | {type}: {N} calls, {N} failures |
| Console Logs | ⚠️ | Via Log Analytics (no direct console access with MCP) |
| Fired Alerts | ✅/⚠️ | {N} in 24h |

### ⚠️ MCP Limitations
- Container App provisioning state and replica count require CLI bootstrap (Step 0)
- Console logs fetched from Log Analytics instead of live container stream
- Recent deployments inferred from Log Analytics events rather than revision API

### ⚠️ Items to Watch
- {any warnings}

### 🔴 Action Required
- {any critical issues}
```

---

## Deep Investigation (only when explicitly requested)

### Container Event Drill-Down

If `ReplicaUnhealthy` appears on the latest revision, pull console logs around the event:

Use MCP tool: `monitor_workspace_log_query`
- subscription: `{SUBSCRIPTION_ID}`
- resource-group: `{RG}`
- workspace: `{LOG_NAME}`
- table: `ContainerAppSystemLogs_CL`
- query: `ContainerAppSystemLogs_CL | where TimeGenerated > ago(24h) and RevisionName_s == '{LATEST_REVISION}' and Reason_s == 'ReplicaUnhealthy' | top 1 by TimeGenerated desc | project UnhealthyTime=TimeGenerated`
- hours: 24

If an event is found, use the returned `UnhealthyTime` in a follow-up query:

Use MCP tool: `monitor_workspace_log_query`
- subscription: `{SUBSCRIPTION_ID}`
- resource-group: `{RG}`
- workspace: `{LOG_NAME}`
- table: `ContainerAppConsoleLogs_CL`
- query: `ContainerAppConsoleLogs_CL | where TimeGenerated between (datetime_add('minute', -30, todatetime('{UNHEALTHY_TIME}')) .. datetime_add('minute', 30, todatetime('{UNHEALTHY_TIME}'))) | project TimeGenerated, Log_s | order by TimeGenerated desc | take 50`
- hours: 24

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

- **Log Analytics table names differ from App Insights**: `AppRequests` not `requests`, `AppExceptions` not `exceptions`, `AppDependencies` not `dependencies`.
- **MCP has no `--offset` issue**: Unlike `az monitor app-insights query`, the MCP `monitor_workspace_log_query` queries Log Analytics directly with no default time clipping. The `hours` parameter controls the window.
- **Step 0 discovery is essential**: MCP tools require explicit subscription ID and resource names — run the CLI discovery block first and substitute the discovered values into each MCP call.
- **Old revision events**: High `ContainerCrashing`/`ReplicaUnhealthy` on old revisions during iterative deploys is normal. Only latest revision warnings matter.
