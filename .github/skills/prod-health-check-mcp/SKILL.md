---
name: prod-health-check-mcp
description: Check Azure production health using Azure MCP tools only (no Azure CLI). Use when user says "check prod with mcp", "mcp health check", or "health check mcp". This is the MCP-only variant for comparison testing.
---

# Production Health Check (Azure MCP Only)

Run a health check against the Azure deployment using **only Azure MCP tools** — no `az` CLI commands.
All checks are read-only. Known limitation: MCP cannot check Container App status (provisioning state, replicas) or console logs.

**Required info**: subscription ID `96e40cb1-d5eb-46c6-b0fd-8e64eb9c119d`, resource group `rg-ltc-dev`.

---

## Step 1: Resource Health (all resources)

Use MCP tool: `resourcehealth_availability-status_list`
- subscription: `96e40cb1-d5eb-46c6-b0fd-8e64eb9c119d`
- resource-group: `rg-ltc-dev`

**Look for**: All resources showing `Available`. Any `Unavailable` or `Degraded` is a critical issue.

**Note**: This replaces the CLI's `az containerapp show` but provides less detail — no provisioning state, replica count, or revision info. It's a binary "available or not" check.

---

## Step 1b: Live Readiness Probe

Run in terminal (curl is not an MCP tool, but this is essential):
```bash
curl -s --max-time 5 -o /dev/null -w "ready_status=%{http_code} response_time=%{time_total}s\n" "https://ca-ltc-api-dev.whiteocean-ee25ad60.centralus.azurecontainerapps.io/ready"
```

**Look for**: `ready_status=200`. If 503, the app reports itself as not ready.

---

## Step 1c: Availability (Synthetic Uptime Test)

Use MCP tool: `monitor_workspace_log_query`
- subscription: `96e40cb1-d5eb-46c6-b0fd-8e64eb9c119d`
- resource-group: `rg-ltc-dev`
- workspace: `log-ltc-dev-8v4tyz`
- table: `AppAvailabilityResults`
- query: `AppAvailabilityResults | where TimeGenerated > ago(24h) | summarize Total=count(), Failed=countif(Success == false), AvgDuration=avg(DurationMs)`
- hours: 24

**Look for**: `Failed` = 0.

---

## Step 2: Request Volume & Latency (24h)

Use MCP tool: `monitor_workspace_log_query`
- subscription: `96e40cb1-d5eb-46c6-b0fd-8e64eb9c119d`
- resource-group: `rg-ltc-dev`
- workspace: `log-ltc-dev-8v4tyz`
- table: `AppRequests`
- query: `AppRequests | where TimeGenerated > ago(24h) | summarize total=count(), failed=countif(Success == false), p95=percentile(DurationMs, 95)`
- hours: 24

**Look for**: `failed` near zero, P95 under 500ms.

---

## Step 2b: Per-Endpoint Latency (24h)

Use MCP tool: `monitor_workspace_log_query`
- subscription: `96e40cb1-d5eb-46c6-b0fd-8e64eb9c119d`
- resource-group: `rg-ltc-dev`
- workspace: `log-ltc-dev-8v4tyz`
- table: `AppRequests`
- query: `AppRequests | where TimeGenerated > ago(24h) | summarize P95=percentile(DurationMs, 95), Count=count() by OperationName | where Count > 10 | order by P95 desc | take 10`
- hours: 24

**Look for**: Any endpoint with P95 > 500ms.

---

## Step 3: HTTP Errors (24h)

Use MCP tool: `monitor_workspace_log_query`
- subscription: `96e40cb1-d5eb-46c6-b0fd-8e64eb9c119d`
- resource-group: `rg-ltc-dev`
- workspace: `log-ltc-dev-8v4tyz`
- table: `AppRequests`
- query: `AppRequests | where TimeGenerated > ago(24h) and toint(ResultCode) >= 400 | summarize Count=count() by ResultCode | order by Count desc | take 10`
- hours: 24

**Look for**: Zero 5xx errors. 4xx should be expected (401, 404).

---

## Step 3b: Error Rate Trend (7d)

Use MCP tool: `monitor_workspace_log_query`
- subscription: `96e40cb1-d5eb-46c6-b0fd-8e64eb9c119d`
- resource-group: `rg-ltc-dev`
- workspace: `log-ltc-dev-8v4tyz`
- table: `AppRequests`
- query: `AppRequests | where TimeGenerated > ago(7d) | summarize Total=count(), Failed=countif(Success == false) by bin(TimeGenerated, 1d) | extend ErrorRate=round(todouble(Failed)/todouble(Total)*100, 2) | order by TimeGenerated desc`
- hours: 168

**Look for**: Rising `ErrorRate` trend. Stable or decreasing = healthy.

---

## Step 4: Exceptions (7d)

Use MCP tool: `monitor_workspace_log_query`
- subscription: `96e40cb1-d5eb-46c6-b0fd-8e64eb9c119d`
- resource-group: `rg-ltc-dev`
- workspace: `log-ltc-dev-8v4tyz`
- table: `AppExceptions`
- query: `AppExceptions | where TimeGenerated > ago(7d) | summarize Count=count() by ExceptionType, OuterMessage | order by Count desc | take 10`
- hours: 168

**Look for**: No recurring exceptions.

---

## Step 5: Container System Events (24h)

Use MCP tool: `monitor_workspace_log_query`
- subscription: `96e40cb1-d5eb-46c6-b0fd-8e64eb9c119d`
- resource-group: `rg-ltc-dev`
- workspace: `log-ltc-dev-8v4tyz`
- table: `ContainerAppSystemLogs_CL`
- query: `ContainerAppSystemLogs_CL | where TimeGenerated > ago(24h) | summarize count() by Reason_s, Type_s | order by count_ desc`
- hours: 24

**Look for**: `ContainerCrashing` or `ReplicaUnhealthy` warnings.

---

## Step 6: Database Metrics (24h)

Use MCP tool: `monitor_metrics_query`
- subscription: `96e40cb1-d5eb-46c6-b0fd-8e64eb9c119d`
- resource-group: `rg-ltc-dev`
- resource: `psql-ltc-dev-8v4tyz`
- resource-type: `Microsoft.DBforPostgreSQL/flexibleServers`
- metric-namespace: `Microsoft.DBforPostgreSQL/flexibleServers`
- metric-names: `cpu_percent,memory_percent,storage_percent,active_connections`
- aggregation: `Average`
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
- subscription: `96e40cb1-d5eb-46c6-b0fd-8e64eb9c119d`
- resource-group: `rg-ltc-dev`
- workspace: `log-ltc-dev-8v4tyz`
- table: `AppDependencies`
- query: `AppDependencies | where TimeGenerated > ago(24h) | summarize Count=count(), FailureCount=countif(Success == false) by DependencyType, Target | order by Count desc | take 10`
- hours: 24

**Look for**: Zero `FailureCount` on PostgreSQL.

---

## Step 8: Console Logs

**⚠️ NOT POSSIBLE WITH MCP** — No Azure MCP tool exists for Container App console logs. This is a known gap.

Fallback: query recent traces from Log Analytics instead:

Use MCP tool: `monitor_workspace_log_query`
- subscription: `96e40cb1-d5eb-46c6-b0fd-8e64eb9c119d`
- resource-group: `rg-ltc-dev`
- workspace: `log-ltc-dev-8v4tyz`
- table: `ContainerAppConsoleLogs_CL`
- query: `ContainerAppConsoleLogs_CL | where TimeGenerated > ago(1h) | project TimeGenerated, Log_s | order by TimeGenerated desc | take 20`
- hours: 1

**Look for**: Only `info` level structured logs. Unhealthy: Python tracebacks, `ERROR` logs.

---

## Step 9: Fired Alerts (24h)

Use MCP tool: `monitor_activitylog_list`
- subscription: `96e40cb1-d5eb-46c6-b0fd-8e64eb9c119d`
- resource-group: `rg-ltc-dev`
- resource-name: `alert-ltc-api-5xx-dev`
- resource-type: `microsoft.insights/scheduledqueryrules`
- hours: 24

**Note**: MCP `monitor_activitylog_list` requires a specific resource name. Check multiple alert resources if needed.

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
| DB CPU | ✅/⚠️ | Avg {X}%, Peak {X}% |
| DB Memory | ✅/⚠️ | Avg {X}%, Peak {X}% |
| DB Storage | ✅ | {X}% used |
| DB Connections | ✅/⚠️ | Avg {X}, Peak {X} (limit: ~120) |
| Dependencies | ✅/⚠️ | {type}: {N} calls, {N} failures |
| Console Logs | ⚠️ | Via Log Analytics (no direct console access with MCP) |
| Fired Alerts | ✅/⚠️ | {N} in 24h |

### ⚠️ MCP Limitations
- Cannot show Container App provisioning state, replica count, or revision info
- Console logs fetched from Log Analytics instead of live container stream
- Alert checking requires specifying each alert resource individually

### ⚠️ Items to Watch
- {any warnings}

### 🔴 Action Required
- {any critical issues}
```

---

## Notes

- **Log Analytics table names differ from App Insights**: `AppRequests` not `requests`, `AppExceptions` not `exceptions`, `AppDependencies` not `dependencies`.
- **MCP has no `--offset` issue**: Unlike `az monitor app-insights query`, the MCP `monitor_workspace_log_query` queries Log Analytics directly with no default time clipping. The `hours` parameter controls the window.
- **Subscription and resource names are hardcoded**: MCP tools require explicit subscription ID and resource names — no shell variable chaining.
