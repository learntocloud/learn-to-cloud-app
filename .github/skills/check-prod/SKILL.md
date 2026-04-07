---
name: check-prod
description: Check Azure production health — app status, errors, latency, database, dependencies. Use when user says "check prod", "how's prod", "hows prod doing", "is prod up", "prod status", "health check", "any errors?", "how's the app doing?", or "check Azure".
---

# Production Health Check

13 checks. One verdict. All read-only. Uses Azure MCP tools.

---

## Prerequisites

Azure MCP tools require `az login` credentials. Before starting, verify:
1. Run `az account show` in terminal to confirm authentication and note the active subscription ID
2. If not authenticated, prompt the user to run `az login`

---

## Verdict Logic

Evaluated top-down, first match wins:

**🔴 Critical** — ANY of: readiness probe non-200, any 5xx in 24h, DB CPU > 80% peak, fired Sev0/Sev1 alerts in 24h, `ContainerCrashing` on current revision, LLM dependency failures > 5 in 24h, any `init.failed` logs in 24h, GitHub API failures > 20 in 24h

**⚠️ Warning** — ANY of: P95 latency > 500ms, DB CPU 50–80% peak or Memory 70–85% or Storage 70–85%, any failed availability tests in 24h, non-zero unhandled exceptions in 7d, active connections > 80, `ReplicaUnhealthy` without matching scale events, error rate spike (single day > 2× weekly average) or rising trend (3+ consecutive days increasing), Container App CPU > 80% or Memory > 80%, ERROR-level AppTraces > 10 in 24h, auth failure rate > 50% in 24h

**✅ Healthy** — none of the above

---

## Step 0: Resource Discovery

Use `az account show` (terminal) to get the active subscription ID. Use resource group `rg-ltc-dev`.

Run in terminal:
```bash
az resource list --resource-group rg-ltc-dev --query "[].{name:name, type:type}" -o table
```

Identify from the output:
- **Container App** — name containing "api" (type `Microsoft.App/containerApps`)
- **Log Analytics workspace** (type `Microsoft.OperationalInsights/workspaces`)
- **PostgreSQL server** (type `Microsoft.DBforPostgreSQL/flexibleServers`)

Then get container app details:
```bash
az containerapp show --name $CA_NAME --resource-group rg-ltc-dev --query "{fqdn:properties.configuration.ingress.fqdn, provisioningState:properties.provisioningState, latestRevision:properties.latestRevisionName, minReplicas:properties.template.scale.minReplicas, maxReplicas:properties.template.scale.maxReplicas}" -o json
```

Save these discovered values — all subsequent steps reference them as `SUBSCRIPTION`, `RG`, `LOG_NAME`, `PSQL_NAME`, `CA_NAME`, `FQDN`, and `LATEST_REVISION`.

---

## Step 1: Live Readiness Probe

Run in terminal:
```bash
curl -s --max-time 5 -o /dev/null -w "ready_status=%{http_code} response_time=%{time_total}s\n" "https://$FQDN/ready"
```

Substitute `$FQDN` with the value from Step 0.

**Verdict**: 🔴 if non-200. ⚠️ if response_time > 2s.

---

## Steps 2–11: MCP Queries

Steps 2–10 are independent reads — **run them all in parallel**.

### Azure MCP Tool Reference

Three MCP tools are used. Call them by setting `command` and passing args in `parameters`:

**Log queries** → `mcp_azure_mcp_monitor` with command `monitor_workspace_log_query`
Required parameters: `resource-group`, `workspace`, `table`, `query`
Optional: `subscription`, `hours`, `limit`

**Metrics** → `mcp_azure_mcp_monitor` with command `monitor_metrics_query`
Required parameters: `resource`, `metric-names`, `metric-namespace`
Optional: `resource-group`, `resource-type`, `subscription`, `interval`, `aggregation`

**Resource Health** → `mcp_azure_mcp_resourcehealth` with command `resourcehealth_availability-status_list`
Required parameters: `resource-group`
Optional: `subscription`

All log queries below use `LOG_NAME` as `workspace` and `rg-ltc-dev` as `resource-group`.

### Step 2: Resource Health (all resources)

Use `mcp_azure_mcp_resourcehealth`:
- command: `resourcehealth_availability-status_list`
- resource-group: `RG`
- subscription: `SUBSCRIPTION`

Quick check for Azure-side platform issues affecting any resource.

**Verdict**: 🔴 if any resource shows `Unavailable`. ⚠️ if `Degraded`.

### Step 3: Availability Tests (24h)

- command: `monitor_workspace_log_query`
- table: `AppAvailabilityResults`
- query: `AppAvailabilityResults | where TimeGenerated > ago(24h) | summarize Total=count(), Failed=countif(Success == false), AvgDuration=avg(DurationMs)`
- hours: 24

**Verdict**: ⚠️ if any Failed > 0. ~288 tests/day expected (3 geo-locations × 5min interval).

### Step 4: Request Health (24h)

- command: `monitor_workspace_log_query`
- table: `AppRequests`
- query: `AppRequests | where TimeGenerated > ago(24h) | summarize P95=percentile(DurationMs, 95), Total=count(), Err4xx=countif(toint(ResultCode) >= 400 and toint(ResultCode) < 500), Err5xx=countif(toint(ResultCode) >= 500)`
- hours: 24

**Verdict**: 🔴 if Err5xx > 0. ⚠️ if P95 > 500ms. 4xx are expected (401, 404).

### Step 5: Error Rate Trend (7d)

- command: `monitor_workspace_log_query`
- table: `AppRequests`
- query: `AppRequests | where TimeGenerated > ago(7d) | summarize Total=count(), Failed=countif(Success == false) by bin(TimeGenerated, 1d) | extend ErrorRate=round(todouble(Failed)/todouble(Total)*100, 2) | order by TimeGenerated desc`
- hours: 168

**Verdict**: ⚠️ if rising trend (3+ consecutive days increasing) or single-day spike > 2× the 7-day average. Stable or falling = healthy.

### Step 6: Errors — Exceptions + AppTraces (7d)

Two queries — run in parallel:

**Query A — Unhandled exceptions** (AppExceptions):

- command: `monitor_workspace_log_query`
- table: `AppExceptions`
- query: `AppExceptions | where TimeGenerated > ago(7d) | summarize Count=count() by ExceptionType, OuterMessage | order by Count desc | take 10`
- hours: 168

**Query B — Caught errors** (AppTraces at ERROR level):

- command: `monitor_workspace_log_query`
- table: `AppTraces`
- query: `AppTraces | where TimeGenerated > ago(24h) and SeverityLevel >= 3 | summarize Count=count() by Message | order by Count desc | take 10`
- hours: 24

**Verdict**: ⚠️ if any recurring exceptions (Query A) or ERROR-level traces > 10 in 24h (Query B).

### Step 7: Dependency Health (24h)

Covers PostgreSQL, Azure OpenAI (via httpx), GitHub API (via httpx), and any other outbound calls.

- command: `monitor_workspace_log_query`
- table: `AppDependencies`
- query: `AppDependencies | where TimeGenerated > ago(24h) | summarize Count=count(), FailureCount=countif(Success == false), AvgDuration=round(avg(DurationMs), 1), P95Duration=round(percentile(DurationMs, 95), 1) by Type, Target | order by Count desc | take 15`
- hours: 24

Expected dependency targets after httpx instrumentation:
- `psql-ltc-dev-*.postgres.database.azure.com|learntocloud` — PostgreSQL (Type: SQL)
- `oai-ltc-dev-*.openai.azure.com` — Azure OpenAI (Type: HTTP or GenAI)
- `api.github.com` — GitHub API for verification checks (Type: HTTP)

**Verdict**: 🔴 if Azure OpenAI failures > 5 or PostgreSQL failures > 0 or GitHub API failures > 20. ⚠️ if any other FailureCount > 0 or LLM P95 > 30s.

### Step 8: Database Metrics (24h)

**Note**: This uses the **metrics** command, not the log query command.

Use `mcp_azure_mcp_monitor` with command `monitor_metrics_query` — run **two calls** (Average + Maximum):

**Call A (Average)**:
- resource: `PSQL_NAME`
- resource-group: `RG`
- subscription: `SUBSCRIPTION`
- resource-type: `Microsoft.DBforPostgreSQL/flexibleServers`
- metric-namespace: `Microsoft.DBforPostgreSQL/flexibleServers`
- metric-names: `cpu_percent,memory_percent,storage_percent,active_connections`
- interval: `PT1H`
- aggregation: `Average`

**Call B (Peak)**: Same as Call A but with aggregation: `Maximum`

Run both calls in parallel.

**Verdict thresholds** (B_Standard_B2s — 2 vCores, 4 GB):

| Metric | ✅ Healthy | ⚠️ Warning | 🔴 Critical |
|--------|-----------|-----------|------------|
| CPU (peak) | < 50% | 50–80% | > 80% |
| Memory (peak) | < 70% | 70–85% | > 85% |
| Storage (peak) | < 70% | 70–85% | > 85% |
| Connections (peak) | < 80 | 80–100 | > 100 |

### Step 9: Container App Metrics (24h)

Use `mcp_azure_mcp_monitor` with command `monitor_metrics_query`:

- resource: `CA_NAME`
- resource-group: `RG`
- subscription: `SUBSCRIPTION`
- resource-type: `Microsoft.App/containerApps`
- metric-namespace: `Microsoft.App/containerApps`
- metric-names: `UsageNanoCores,WorkingSetBytes,RestartCount`
- interval: `PT1H`
- aggregation: `Maximum`

**Verdict thresholds** (0.5 CPU / 1Gi memory allocated):

| Metric | ✅ Healthy | ⚠️ Warning | 🔴 Critical |
|--------|-----------|-----------|------------|
| CPU (UsageNanoCores peak) | < 300M | 300M–400M | > 400M (80% of 500M) |
| Memory (WorkingSetBytes peak) | < 750Mi | 750Mi–860Mi | > 860Mi (80% of 1Gi) |
| RestartCount (total) | 0 | 1–2 | > 2 |

### Step 10: Container Stability (24h)

Substitute `LATEST_REVISION` from Step 0 into the KQL query.

- command: `monitor_workspace_log_query`
- table: `ContainerAppSystemLogs_CL`
- query: `ContainerAppSystemLogs_CL | where TimeGenerated > ago(24h) and RevisionName_s == 'LATEST_REVISION_VALUE' | summarize Count=count() by Reason_s, Type_s | order by Count desc`
- hours: 24

Replace `LATEST_REVISION_VALUE` with the actual revision name.

**Fallback**: If `ContainerAppSystemLogs_CL` returns no results, try `ContainerAppSystemLogs` (without `_CL`) with column names `Reason` and `Type` instead of `Reason_s` and `Type_s`:
```
ContainerAppSystemLogs | where TimeGenerated > ago(24h) and RevisionName == 'LATEST_REVISION_VALUE' | summarize Count=count() by Reason, Type | order by Count desc
```

**Verdict**: 🔴 if `ContainerCrashing`. ⚠️ if `ReplicaUnhealthy` — a few events alongside `SuccessfulRescale` is normal scale-in/out; sustained events without scaling suggest health probe failures.

### Step 11: Fired Alerts (24h)

- command: `monitor_workspace_log_query`
- table: `AzureActivity`
- query: `AzureActivity | where TimeGenerated > ago(24h) | where OperationNameValue has "microsoft.insights/metricalerts" or OperationNameValue has "microsoft.insights/scheduledqueryrules" | where ActivityStatusValue == "Activated" | extend AlertName=tostring(split(ResourceId, "/")[-1]) | project TimeGenerated, AlertName, ResourceId, Properties | order by TimeGenerated desc`
- hours: 24

Known alert names from Terraform (match against `AlertName`):
- **Sev0**: `alert-ltc-availability-*` (app unreachable)
- **Sev1**: `alert-ltc-api-5xx-*`, `alert-ltc-api-restarts-*`, `alert-ltc-db-connections-*`, `alert-ltc-llm-failures-*`, `alert-ltc-init-failed-*`
- **Sev2**: `alert-ltc-api-cpu-*`, `alert-ltc-api-memory-*`, `alert-ltc-api-latency-*`, `alert-ltc-db-storage-*`, `alert-ltc-db-cpu-*`, `alert-ltc-api-4xx-*`

**Verdict**: 🔴 if any Sev0/Sev1 alert names appear. ⚠️ if Sev2 alerts fired.

### Step 12: Business Metrics (24h)

Custom OTel counters for key domain events.

- command: `monitor_workspace_log_query`
- table: `AppMetrics`
- query: `AppMetrics | where TimeGenerated > ago(24h) and Name in ('auth.login', 'submission.daily_limit_exceeded', 'submission.cooldown_active', 'user.deletion', 'step.completed', 'verification.attempt') | summarize Total=sum(Sum) by Name | order by Name asc`
- hours: 24

Also check auth success/failure ratio:

- command: `monitor_workspace_log_query`
- table: `AppMetrics`
- query: `AppMetrics | where TimeGenerated > ago(24h) and Name == 'auth.login' | extend result = tostring(Properties['result']) | summarize Total=sum(Sum) by result`
- hours: 24

**Verdict**: ⚠️ if auth failure rate > 50% (possible GitHub OAuth outage) or daily_limit_exceeded > 50 (capacity pressure). Include totals in report for situational awareness.

### Step 13: LLM Performance (24h)

GenAI-specific metrics from the agent framework.

- command: `monitor_workspace_log_query`
- table: `AppMetrics`
- query: `AppMetrics | where TimeGenerated > ago(24h) and Name in ('gen_ai.client.token.usage', 'gen_ai.client.operation.duration') | summarize Total=sum(Sum), AvgValue=round(avg(Sum), 2) by Name`
- hours: 24

**Verdict**: Informational — include token usage and operation duration in the report. ⚠️ if avg operation duration > 60s.

---

## Summary Report

```
## Production Health Report — {date}

### Overall: ✅ Healthy / ⚠️ Warning / 🔴 Critical

**Verdict reasoning**: {1-2 sentence explanation citing specific check(s)}

| # | Check | Status | Details |
|---|-------|--------|---------|
| 1 | Readiness Probe | ✅/🔴 | {status_code}, {X}s response |
| 2 | Resource Health | ✅/🔴 | {Available/Degraded/Unavailable} |
| 3 | Availability Tests | ✅/⚠️ | {N} total, {N} failed in 24h |
| 4 | Request Health | ✅/🔴 | P95 {X}ms, {N} 4xx, {N} 5xx |
| 5 | Error Rate Trend | ✅/⚠️ | {stable/rising/falling} over 7d |
| 6 | Errors | ✅/⚠️ | {N} exceptions in 7d, {N} error traces in 24h |
| 7 | Dependencies | ✅/⚠️/🔴 | PostgreSQL: {N}/{N}fail, OpenAI: {N}/{N}fail P95 {X}ms, GitHub: {N}/{N}fail |
| 8 | Database | ✅/⚠️/🔴 | CPU {X}%, Mem {X}%, Storage {X}%, Conn {X} |
| 9 | Container App | ✅/⚠️/🔴 | CPU {X}nc, Mem {X}B, Restarts {N} |
| 10 | Container Stability | ✅/⚠️ | Rev: {rev}, {events} |
| 11 | Fired Alerts | ✅/🔴 | {N} in 24h, names: {list} |
| 12 | Business Metrics | ✅/⚠️ | Logins: {N}✓/{N}✗, Steps: {N}, Verifications: {N}, Deletions: {N} |
| 13 | LLM Performance | ✅/⚠️ | Tokens: {N}, Avg duration: {X}s |

### ⚠️ Items to Watch
- {any warnings — omit if none}

### 🔴 Action Required
- {any critical issues — omit if none}
```

---

## Notes

- **MCP tools used**: `mcp_azure_mcp_monitor` (log queries via `monitor_workspace_log_query`, metrics via `monitor_metrics_query`) and `mcp_azure_mcp_resourcehealth` (platform health via `resourcehealth_availability-status_list`). Step 1 uses `curl` in terminal.
- **Log Analytics table names**: Use `AppRequests`, `AppExceptions`, `AppDependencies`, `AppAvailabilityResults` (Application Insights workspace-mode tables, not legacy `requests`/`exceptions`/`dependencies`).
- **Metrics vs logs**: Steps 8–9 query Azure Monitor **metrics** (command `monitor_metrics_query`). Steps 3–7, 10–11 query Log Analytics **logs** (command `monitor_workspace_log_query`). These are different MCP commands.
- **Container App system logs**: Table may be `ContainerAppSystemLogs_CL` (custom log, `_s` suffix columns) or `ContainerAppSystemLogs` (standard, no suffix). Step 10 includes a fallback query for both schemas.
- **Parallelization**: Steps 2–13 have no dependencies on each other — run them all concurrently in parallel MCP calls.
- **Alert severity mapping**: Step 11 maps `AlertName` → severity using the known Terraform-defined alert names rather than parsing severity from the activity log (which doesn't expose it directly).
