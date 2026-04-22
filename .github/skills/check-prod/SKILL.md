---
name: check-prod
description: Check Azure production health — app status, errors, latency, database, dependencies. Use when user says "check prod", "how's prod", "hows prod doing", "is prod up", "prod status", "health check", "any errors?", "how's the app doing?", or "check Azure".
---

# Production Health Check

14 checks. One verdict. All read-only. Uses `az` CLI (no MCP dependency).

---

## Prerequisites

Before starting, verify Azure CLI authentication:
1. Run `az account show` in terminal to confirm authentication and note the active subscription ID
2. If not authenticated, prompt the user to run `az login`

---

## Verdict Logic

Evaluated top-down, first match wins:

**🔴 Critical** — ANY of: readiness probe non-200, any 5xx in 24h, DB CPU > 80% sustained, DB CPU credits < 10, fired Sev0/Sev1 alerts in 24h, `ContainerCrashing` on current revision, any `init.failed` logs in 24h, GitHub API failures > 20 in 24h

**⚠️ Warning** — ANY of: P95 latency > 500ms, DB CPU 50–80% peak or Memory 70–85% or Storage 70–85% or CPU credits 10–30, any failed availability tests in 24h, non-zero unhandled exceptions in 7d, active connections > 30 (B1ms max 50), `ReplicaUnhealthy` without matching scale events, error rate spike (single day > 2× weekly average) or rising trend (3+ consecutive days increasing), Container App CPU > 80% or Memory > 80%, ERROR-level AppTraces > 10 in 24h, auth failure rate > 50% in 24h

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
- **Application Insights** (type `microsoft.insights/components`)

Then get container app details:
```bash
az containerapp show --name $CA_NAME --resource-group rg-ltc-dev --query "{fqdn:properties.configuration.ingress.fqdn, provisioningState:properties.provisioningState, latestRevision:properties.latestRevisionName, minReplicas:properties.template.scale.minReplicas, maxReplicas:properties.template.scale.maxReplicas}" -o json
```

Save these discovered values — all subsequent steps reference them as `SUBSCRIPTION`, `RG`, `LOG_NAME`, `PSQL_NAME`, `CA_NAME`, `APPI_NAME`, `FQDN`, and `LATEST_REVISION`.

---

## Step 1: Live Readiness Probe

Run in terminal:
```bash
curl -s --max-time 5 -o /dev/null -w "ready_status=%{http_code} response_time=%{time_total}s\n" "https://$FQDN/ready"
```

Substitute `$FQDN` with the value from Step 0.

**Verdict**: 🔴 if non-200. ⚠️ if response_time > 2s.

---

## Steps 2–14: CLI Queries

Steps 2–14 are independent reads — **run them all in parallel** using separate terminal calls.

### Common Variables

Set these once for all subsequent commands:
```bash
# Use values from Step 0:
# RG, LOG_NAME, PSQL_NAME, CA_NAME, APPI_NAME, SUBSCRIPTION
```

### Step 2: Resource Health (all resources)

```bash
az resource health availability-status list-by-resource-group --resource-group $RG --subscription $SUBSCRIPTION -o json 2>/dev/null || echo "[]"
```

Quick check for Azure-side platform issues affecting any resource.

**Verdict**: 🔴 if any resource shows `Unavailable`. ⚠️ if `Degraded`.

### Step 3: Availability Tests (24h)

```bash
az monitor log-analytics query -w $LOG_NAME --analytics-query "AppAvailabilityResults | where TimeGenerated > ago(24h) | summarize Total=count(), Failed=countif(Success == false), AvgDuration=avg(DurationMs)" -o json
```

**Verdict**: ⚠️ if any Failed > 0. ~288 tests/day expected (3 geo-locations × 5min interval).

### Step 4: Request Health (24h)

```bash
az monitor log-analytics query -w $LOG_NAME --analytics-query "AppRequests | where TimeGenerated > ago(24h) | summarize P95=percentile(DurationMs, 95), Total=count(), Err4xx=countif(toint(ResultCode) >= 400 and toint(ResultCode) < 500), Err5xx=countif(toint(ResultCode) >= 500)" -o json
```

**Verdict**: 🔴 if Err5xx > 0. ⚠️ if P95 > 500ms. 4xx are expected (401, 404).

### Step 5: Error Rate Trend (7d)

```bash
az monitor log-analytics query -w $LOG_NAME --analytics-query "AppRequests | where TimeGenerated > ago(7d) | summarize Total=count(), Failed=countif(Success == false) by bin(TimeGenerated, 1d) | extend ErrorRate=round(todouble(Failed)/todouble(Total)*100, 2) | order by TimeGenerated desc" -o json
```

**Verdict**: ⚠️ if rising trend (3+ consecutive days increasing) or single-day spike > 2× the 7-day average. Stable or falling = healthy.

### Step 6: Errors — Exceptions + AppTraces (7d)

Two queries — run in parallel:

**Query A — Unhandled exceptions** (AppExceptions):

```bash
az monitor log-analytics query -w $LOG_NAME --analytics-query "AppExceptions | where TimeGenerated > ago(7d) | summarize Count=count() by ExceptionType, OuterMessage | order by Count desc | take 10" -o json
```

**Query B — Caught errors** (AppTraces at ERROR level):

```bash
az monitor log-analytics query -w $LOG_NAME --analytics-query "AppTraces | where TimeGenerated > ago(24h) and SeverityLevel >= 3 | summarize Count=count() by Message | order by Count desc | take 10" -o json
```

**Verdict**: ⚠️ if any recurring exceptions (Query A) or ERROR-level traces > 10 in 24h (Query B).

### Step 7: Dependency Health (24h)

Covers PostgreSQL, GitHub API (via httpx), and any other outbound calls.

```bash
az monitor log-analytics query -w $LOG_NAME --analytics-query "AppDependencies | where TimeGenerated > ago(24h) | summarize Count=count(), FailureCount=countif(Success == false), AvgDuration=round(avg(DurationMs), 1), P95Duration=round(percentile(DurationMs, 95), 1) by Type, Target | order by Count desc | take 15" -o json
```

Expected dependency targets:
- `psql-ltc-dev-*.postgres.database.azure.com|learntocloud` — PostgreSQL (Type: SQL)
- `api.github.com` — GitHub API for verification checks (Type: HTTP)

**Verdict**: 🔴 if PostgreSQL failures > 0 or GitHub API failures > 20. ⚠️ if any other FailureCount > 0.

### Step 8: Database Metrics (24h)

**Note**: These use `az monitor metrics list`, not log queries.

Run **three calls** in parallel — Average, Maximum, and CPU credits:

**Call A (Average)**:
```bash
az monitor metrics list --resource $PSQL_NAME --resource-group $RG --resource-type "Microsoft.DBforPostgreSQL/flexibleServers" --metrics "cpu_percent" "memory_percent" "storage_percent" "active_connections" --interval PT1H --aggregation Average --start-time $(date -u -d '24 hours ago' +%Y-%m-%dT%H:%M:%SZ) --end-time $(date -u +%Y-%m-%dT%H:%M:%SZ) -o json
```

**Call B (Peak)**:
Same as Call A but with `--aggregation Maximum`.

**Call C (CPU Credits — burstable tier)**:
```bash
az monitor metrics list --resource $PSQL_NAME --resource-group $RG --resource-type "Microsoft.DBforPostgreSQL/flexibleServers" --metrics "cpu_credits_remaining" "cpu_credits_consumed" --interval PT1H --aggregation Minimum --start-time $(date -u -d '24 hours ago' +%Y-%m-%dT%H:%M:%SZ) --end-time $(date -u +%Y-%m-%dT%H:%M:%SZ) -o json
```

**Verdict thresholds** (B_Standard_B1ms — 1 vCore, 2 GB RAM, burstable):

| Metric | ✅ Healthy | ⚠️ Warning | 🔴 Critical |
|--------|-----------|-----------|------------|
| CPU (peak) | < 50% | 50–80% | > 80% |
| Memory (peak) | < 70% | 70–85% | > 85% |
| Storage (peak) | < 70% | 70–85% | > 85% |
| Connections (peak) | < 80 | 80–100 | > 100 |
| CPU credits remaining (min) | > 30 | 10–30 | < 10 |

### Step 9: Container App Metrics (24h)

```bash
az monitor metrics list --resource $CA_NAME --resource-group $RG --resource-type "Microsoft.App/containerApps" --metrics "UsageNanoCores" "WorkingSetBytes" --interval PT1H --aggregation Maximum --start-time $(date -u -d '24 hours ago' +%Y-%m-%dT%H:%M:%SZ) --end-time $(date -u +%Y-%m-%dT%H:%M:%SZ) -o json
```

**Verdict thresholds** (0.5 CPU / 1Gi memory allocated):

| Metric | ✅ Healthy | ⚠️ Warning | 🔴 Critical |
|--------|-----------|-----------|------------|
| CPU (UsageNanoCores peak) | < 300M | 300M–400M | > 400M (80% of 500M) |
| Memory (WorkingSetBytes peak) | < 750Mi | 750Mi–860Mi | > 860Mi (80% of 1Gi) |

### Step 10: Container Stability (24h)

Substitute `LATEST_REVISION` from Step 0 into the query.

```bash
az monitor log-analytics query -w $LOG_NAME --analytics-query "ContainerAppSystemLogs_CL | where TimeGenerated > ago(24h) and RevisionName_s == 'LATEST_REVISION_VALUE' | summarize Count=count() by Reason_s, Type_s | order by Count desc" -o json
```

Replace `LATEST_REVISION_VALUE` with the actual revision name.

**Fallback**: If `ContainerAppSystemLogs_CL` returns no results, try `ContainerAppSystemLogs` (without `_CL`) with column names `Reason` and `Type` instead of `Reason_s` and `Type_s`:
```bash
az monitor log-analytics query -w $LOG_NAME --analytics-query "ContainerAppSystemLogs | where TimeGenerated > ago(24h) and RevisionName == 'LATEST_REVISION_VALUE' | summarize Count=count() by Reason, Type | order by Count desc" -o json
```

**Verdict**: 🔴 if `ContainerCrashing` or `OOMKilled`. ⚠️ if `ReplicaUnhealthy` — a few events alongside `SuccessfulRescale` is normal scale-in/out; sustained events without scaling suggest health probe failures.

### Step 11: Fired Alerts (24h)

```bash
az monitor log-analytics query -w $LOG_NAME --analytics-query "AzureActivity | where TimeGenerated > ago(24h) | where OperationNameValue has 'microsoft.insights/metricalerts' or OperationNameValue has 'microsoft.insights/scheduledqueryrules' | where ActivityStatusValue == 'Activated' | extend AlertName=tostring(split(ResourceId, '/')[-1]) | project TimeGenerated, AlertName, ResourceId, Properties | order by TimeGenerated desc" -o json
```

Known alert names from Terraform (match against `AlertName`):
- **Sev0**: `alert-ltc-availability-*` (app unreachable)
- **Sev1**: `alert-ltc-api-5xx-*`, `alert-ltc-api-restarts-*`, `alert-ltc-db-connections-*`, `alert-ltc-db-credits-*`, `alert-ltc-init-failed-*`
- **Sev2**: `alert-ltc-api-cpu-*`, `alert-ltc-api-memory-*`, `alert-ltc-api-latency-*`, `alert-ltc-api-4xx-*`, `alert-ltc-db-storage-*`, `alert-ltc-db-cpu-*`

**Verdict**: 🔴 if any Sev0/Sev1 alert names appear. ⚠️ if Sev2 alerts fired.

### Step 12: Business Metrics (24h)

Custom OTel counters for key domain events.

```bash
az monitor log-analytics query -w $LOG_NAME --analytics-query "AppMetrics | where TimeGenerated > ago(24h) and Name in ('auth.login', 'submission.cooldown_active', 'user.deletion', 'step.completed', 'verification.attempt') | summarize Total=sum(Sum) by Name | order by Name asc" -o json
```

Also check auth success/failure ratio:

```bash
az monitor log-analytics query -w $LOG_NAME --analytics-query "AppMetrics | where TimeGenerated > ago(24h) and Name == 'auth.login' | extend result = tostring(Properties['result']) | summarize Total=sum(Sum) by result" -o json
```

**Verdict**: ⚠️ if auth failure rate > 50% (possible GitHub OAuth outage). Include totals in report for situational awareness.

### Step 13: Console Log Errors (24h)

Check container stdout/stderr for crash indicators.

```bash
az monitor log-analytics query -w $LOG_NAME --analytics-query "ContainerAppConsoleLogs_CL | where TimeGenerated > ago(24h) | where Log_s has 'Traceback' or Log_s has 'FATAL' or Log_s has 'OOMKilled' or Log_s has 'Segmentation fault' | summarize Count=count() by bin(TimeGenerated, 1h) | order by TimeGenerated desc" -o json
```

**Fallback**: If `ContainerAppConsoleLogs_CL` returns no results, try `ContainerAppConsoleLogs`:
```bash
az monitor log-analytics query -w $LOG_NAME --analytics-query "ContainerAppConsoleLogs | where TimeGenerated > ago(24h) | where Log has 'Traceback' or Log has 'FATAL' or Log has 'OOMKilled' or Log has 'Segmentation fault' | summarize Count=count() by bin(TimeGenerated, 1h) | order by TimeGenerated desc" -o json
```

**Verdict**: 🔴 if any OOMKilled or Segfault. ⚠️ if recurring Tracebacks (> 5 in 24h).

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
| 7 | Dependencies | ✅/⚠️/🔴 | PostgreSQL: {N}/{N}fail, GitHub: {N}/{N}fail |
| 8 | Database | ✅/⚠️/🔴 | CPU {X}%, Mem {X}%, Storage {X}%, Conn {X}, Credits {X} |
| 9 | Container App | ✅/⚠️/🔴 | CPU {X}nc, Mem {X}B |
| 10 | Container Stability | ✅/⚠️ | Rev: {rev}, {events} |
| 11 | Fired Alerts | ✅/🔴 | {N} in 24h, names: {list} |
| 12 | Business Metrics | ✅/⚠️ | Logins: {N}✓/{N}✗, Steps: {N}, Verifications: {N}, Deletions: {N} |
| 13 | Console Errors | ✅/⚠️/🔴 | {N} crashes, {N} tracebacks in 24h |

### ⚠️ Items to Watch
- {any warnings — omit if none}

### 🔴 Action Required
- {any critical issues — omit if none}
```

---

## Notes

- **CLI tools used**: `az monitor log-analytics query` for log queries, `az monitor metrics list` for metrics, `az resource health` for platform health. Step 1 uses `curl`.
- **No MCP dependency**: This skill uses only `az` CLI, which requires `az login` (already a prerequisite). Works without the azure-skills plugin installed.
- **Log Analytics table names**: Use `AppRequests`, `AppExceptions`, `AppDependencies`, `AppAvailabilityResults` (Application Insights workspace-mode tables).
- **Metrics vs logs**: Steps 8–9 query Azure Monitor **metrics** (`az monitor metrics list`). Steps 3–7, 10–14 query Log Analytics **logs** (`az monitor log-analytics query`). These are different CLI commands.
- **Container App system logs**: Table may be `ContainerAppSystemLogs_CL` (custom log, `_s` suffix columns) or `ContainerAppSystemLogs` (standard, no suffix). Steps 10 and 14 include fallback queries for both schemas.
- **Parallelization**: Steps 2–14 have no dependencies on each other — run them all concurrently.
- **Alert severity mapping**: Step 11 maps `AlertName` → severity using Terraform-defined alert names.
- **Infrastructure tier**: PostgreSQL is B_Standard_B1ms (1 vCore, 2 GB, burstable). Container App is 0.5 CPU / 1 Gi, 1–2 replicas. Thresholds are tuned for these SKUs.
