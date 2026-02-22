---
name: prod-health-check-mcp
description: Check Azure production health using Azure MCP tools. Use when user says "check prod with mcp", "mcp health check", or "health check mcp".
---

# Production Health Check (MCP)

10 checks. One verdict. All read-only. Uses Azure MCP tools with a one-time CLI bootstrap for resource discovery.

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

Run this CLI block once to discover resource names and container app status. Use the discovered values in all subsequent MCP tool calls.

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

if [ -z "$CA_NAME" ] || [ -z "$LOG_NAME" ] || [ -z "$PSQL_NAME" ]; then
  echo "ERROR: Could not discover all required resources in RG=$RG" >&2
  echo "CA_NAME=$CA_NAME LOG_NAME=$LOG_NAME PSQL_NAME=$PSQL_NAME" >&2
  exit 1
fi

# Container app status details (closes parity gap with CLI skill)
az containerapp show -n $CA_NAME -g $RG \
  --query "{provisioningState:properties.provisioningState, runningStatus:properties.runningStatus, latestRevision:properties.latestRevisionName, fqdn:properties.configuration.ingress.fqdn, minReplicas:properties.template.scale.minReplicas, maxReplicas:properties.template.scale.maxReplicas}" \
  -o json

FQDN=$(az containerapp show -n $CA_NAME -g $RG --query properties.configuration.ingress.fqdn -o tsv)
LATEST_REVISION=$(az containerapp show -n $CA_NAME -g $RG --query properties.latestRevisionName -o tsv)

echo "SUBSCRIPTION_ID=$SUBSCRIPTION_ID"
echo "RG=$RG"
echo "CA_NAME=$CA_NAME"
echo "LOG_NAME=$LOG_NAME"
echo "PSQL_NAME=$PSQL_NAME"
echo "FQDN=$FQDN"
echo "LATEST_REVISION=$LATEST_REVISION"
```

Save the discovered values. Use them as the `subscription`, `resource-group`, `workspace`, `resource`, and `resource-name` parameters in all MCP tool calls below.

---

## Step 1: Container App Status + Live Readiness Probe

Container app status was already captured in Step 0 (provisioning state, replicas, revision). Report those values.

Run in terminal for the live readiness probe:
```bash
curl -s --max-time 5 -o /dev/null -w "ready_status=%{http_code} response_time=%{time_total}s\n" "https://{FQDN}/ready"
```

**Look for**: `provisioningState: Succeeded`, `runningStatus: Running`, replica count ≥ 1. `ready_status=200`. If 503, the app reports itself as not ready (check DB connectivity or init errors). Response time > 2s is a warning.

---

## Step 2: Availability Tests (24h)

Use MCP tool: `monitor_workspace_log_query`
- subscription: `{SUBSCRIPTION_ID}`
- resource-group: `{RG}`
- workspace: `{LOG_NAME}`
- table: `AppAvailabilityResults`
- query: `AppAvailabilityResults | where TimeGenerated > ago(24h) | summarize Total=count(), Failed=countif(Success == false), AvgDuration=avg(DurationMs)`
- hours: 24

**Look for**: `Failed` = 0. Availability tests run every 5 minutes from multiple regions — ~288 tests/day. Any failures indicate real downtime visible to users.

---

## Step 3: Request Latency P95 (24h)

Use MCP tool: `monitor_workspace_log_query`
- subscription: `{SUBSCRIPTION_ID}`
- resource-group: `{RG}`
- workspace: `{LOG_NAME}`
- table: `AppRequests`
- query: `AppRequests | where TimeGenerated > ago(24h) | summarize p95=percentile(DurationMs, 95)`
- hours: 24

**Look for**: P95 under 500ms.

---

## Step 4: HTTP Errors (24h)

Use MCP tool: `monitor_workspace_log_query`
- subscription: `{SUBSCRIPTION_ID}`
- resource-group: `{RG}`
- workspace: `{LOG_NAME}`
- table: `AppRequests`
- query: `AppRequests | where TimeGenerated > ago(24h) and toint(ResultCode) >= 400 | summarize Count=count() by ResultCode | order by Count desc | take 10`
- hours: 24

**Look for**: Zero 5xx errors. 4xx should be expected (401, 404).

---

## Step 5: Error Rate Trend (7d)

Use MCP tool: `monitor_workspace_log_query`
- subscription: `{SUBSCRIPTION_ID}`
- resource-group: `{RG}`
- workspace: `{LOG_NAME}`
- table: `AppRequests`
- query: `AppRequests | where TimeGenerated > ago(7d) | summarize Total=count(), Failed=countif(Success == false) by bin(TimeGenerated, 1d) | extend ErrorRate=round(todouble(Failed)/todouble(Total)*100, 2) | order by TimeGenerated desc`
- hours: 168

**Look for**: Rising `ErrorRate` trend even if each day is below the alert threshold. Stable or decreasing = healthy.

---

## Step 6: Unhandled Exceptions (7d)

Use MCP tool: `monitor_workspace_log_query`
- subscription: `{SUBSCRIPTION_ID}`
- resource-group: `{RG}`
- workspace: `{LOG_NAME}`
- table: `AppExceptions`
- query: `AppExceptions | where TimeGenerated > ago(7d) | summarize Count=count() by ExceptionType, OuterMessage | order by Count desc | take 10`
- hours: 168

**Look for**: No recurring exceptions.

---

## Step 7: Database Metrics (24h)

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

## Step 8: Dependency Health (24h)

Use MCP tool: `monitor_workspace_log_query`
- subscription: `{SUBSCRIPTION_ID}`
- resource-group: `{RG}`
- workspace: `{LOG_NAME}`
- table: `AppDependencies`
- query: `AppDependencies | where TimeGenerated > ago(24h) | summarize Count=count(), FailureCount=countif(Success == false) by DependencyType, Target | order by Count desc | take 10`
- hours: 24

**Look for**: Zero `FailureCount` on PostgreSQL. Any HTTP dependency failures (GitHub API, OpenAI).

---

## Step 9: Container Stability (24h)

Use the `LATEST_REVISION` value from Step 0 discovery.

Use MCP tool: `monitor_workspace_log_query`
- subscription: `{SUBSCRIPTION_ID}`
- resource-group: `{RG}`
- workspace: `{LOG_NAME}`
- table: `ContainerAppSystemLogs_CL`
- query: `ContainerAppSystemLogs_CL | where TimeGenerated > ago(24h) and RevisionName_s == '{LATEST_REVISION}' | summarize Count=count() by Reason_s, Type_s | order by Count desc`
- hours: 24

**Look for**: `ContainerCrashing` or `ReplicaUnhealthy` on the current revision is concerning. Events on old revisions during iterative deploys are expected — this query filters to the current revision only.

---

## Step 10: Fired Alerts (24h)

Use MCP tool: `monitor_workspace_log_query`
- subscription: `{SUBSCRIPTION_ID}`
- resource-group: `{RG}`
- workspace: `{LOG_NAME}`
- table: `AzureActivity`
- query: `AzureActivity | where TimeGenerated > ago(24h) | where OperationNameValue has "microsoft.insights/metricalerts" or OperationNameValue has "microsoft.insights/scheduledqueryrules" | where ActivityStatusValue == "Activated" | project TimeGenerated, OperationName, ResourceId | order by TimeGenerated desc`
- hours: 24

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

- **Log Analytics table names differ from App Insights**: `AppRequests` not `requests`, `AppExceptions` not `exceptions`, `AppDependencies` not `dependencies`.
- **MCP has no `--offset` issue**: Unlike `az monitor app-insights query`, the MCP `monitor_workspace_log_query` queries Log Analytics directly with no default time clipping. The `hours` parameter controls the window.
- **Step 0 discovery is essential**: MCP tools require explicit subscription ID and resource names — run the CLI discovery block first and substitute the discovered values into each MCP call.
- **Old revision events**: Step 9 filters to the current revision only. `ContainerCrashing`/`ReplicaUnhealthy` on old revisions during iterative deploys is normal and excluded.
