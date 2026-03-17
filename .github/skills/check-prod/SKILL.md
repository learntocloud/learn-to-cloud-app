---
name: check-prod
description: Check Azure production health — app status, errors, latency, database, dependencies. Use when user says "check prod", "how's prod", "hows prod doing", "is prod up", "prod status", "health check", "any errors?", "how's the app doing?", or "check Azure".
---

# Production Health Check

9 checks. One verdict. All read-only. Uses Azure MCP tools.

---

## Prerequisites

Azure MCP tools require `az login` credentials. Before starting, verify:
1. User is authenticated (`az account show` succeeds or Azure MCP can list resources)
2. Subscription from `infra/terraform.tfvars` is accessible

If Azure MCP tools are unavailable, prompt the user to install the Azure MCP extension or start the Azure MCP Server.

---

## Verdict Logic

Evaluated top-down, first match wins:

**🔴 Critical** — ANY of: readiness probe non-200, any 5xx in 24h, DB CPU > 80% peak, fired Sev0/Sev1 alerts in 24h, `ContainerCrashing` on current revision

**⚠️ Warning** — ANY of: P95 latency > 500ms, DB CPU 50–80% peak or Memory 70–85% or Storage 70–85%, any failed availability tests in 24h, non-zero unhandled exceptions in 7d, active connections > 80, `ReplicaUnhealthy` without matching scale events, error rate spike (single day > 2× weekly average) or rising trend (3+ consecutive days increasing)

**✅ Healthy** — none of the above

---

## Step 0: Resource Discovery

Read the subscription ID from `infra/terraform.tfvars` (`subscription_id` field). Use resource group `rg-ltc-dev`.

List resources in the resource group using `az resource list --resource-group rg-ltc-dev --subscription $SUBSCRIPTION_ID` to identify:
- **Container App** — name containing "api" (type `Microsoft.App/containerApps`)
- **Log Analytics workspace** (type `Microsoft.OperationalInsights/workspaces`)
- **PostgreSQL server** (type `Microsoft.DBforPostgreSQL/flexibleServers`)

Then get the container app details using `az containerapp show`: provisioning state, running status, latest revision name, FQDN, min/max replicas.

Save these discovered values — all subsequent steps reference them as `SUBSCRIPTION`, `RG`, `LOG_NAME`, `PSQL_NAME`, `FQDN`, and `LATEST_REVISION`.

---

## Step 1: Live Readiness Probe

Run in terminal:
```bash
curl -s --max-time 5 -o /dev/null -w "ready_status=%{http_code} response_time=%{time_total}s\n" "https://$FQDN/ready"
```

Substitute `$FQDN` with the value from Step 0.

**Verdict**: 🔴 if non-200. ⚠️ if response_time > 2s.

---

## Steps 2–8: Log Analytics & Metrics Queries

Steps 2–7 are independent reads — **run them in parallel** where possible.

All Log Analytics queries need:
- resource-group: `RG` from Step 0
- workspace: `LOG_NAME` from Step 0
- subscription: `SUBSCRIPTION` from Step 0
- table: specified per step below
- query: specified per step below
- hours: specified per step below

Use the Azure MCP monitor tool to query Log Analytics.

### Step 2: Availability Tests (24h)

- table: `AppAvailabilityResults`
- query: `AppAvailabilityResults | where TimeGenerated > ago(24h) | summarize Total=count(), Failed=countif(Success == false), AvgDuration=avg(DurationMs)`
- hours: 24

**Verdict**: ⚠️ if any Failed > 0. ~288 tests/day expected.

### Step 3: Request Health (24h)

Single query for both latency and error breakdown:

- table: `AppRequests`
- query: `AppRequests | where TimeGenerated > ago(24h) | summarize P95=percentile(DurationMs, 95), Total=count(), Err4xx=countif(toint(ResultCode) >= 400 and toint(ResultCode) < 500), Err5xx=countif(toint(ResultCode) >= 500)`
- hours: 24

**Verdict**: 🔴 if Err5xx > 0. ⚠️ if P95 > 500ms. 4xx are expected (401, 404).

### Step 4: Error Rate Trend (7d)

- table: `AppRequests`
- query: `AppRequests | where TimeGenerated > ago(7d) | summarize Total=count(), Failed=countif(Success == false) by bin(TimeGenerated, 1d) | extend ErrorRate=round(todouble(Failed)/todouble(Total)*100, 2) | order by TimeGenerated desc`
- hours: 168

**Verdict**: ⚠️ if rising trend (3+ consecutive days increasing) or single-day spike > 2× the 7-day average. Stable or falling = healthy.

### Step 5: Unhandled Exceptions (7d)

- table: `AppExceptions`
- query: `AppExceptions | where TimeGenerated > ago(7d) | summarize Count=count() by ExceptionType, OuterMessage | order by Count desc | take 10`
- hours: 168

**Verdict**: ⚠️ if any recurring exceptions.

### Step 6: Dependency Health (24h)

- table: `AppDependencies`
- query: `AppDependencies | where TimeGenerated > ago(24h) | summarize Count=count(), FailureCount=countif(Success == false) by DependencyType, Target | order by Count desc | take 10`
- hours: 24

**Verdict**: ⚠️ if any FailureCount > 0, especially on PostgreSQL.

### Step 7: Database Metrics (24h)

**Note**: This step queries Azure Monitor **metrics** (not Log Analytics logs). Use the Azure MCP monitor tool's metrics query capability.

Query metrics for the PostgreSQL server. Run two queries — average and peak:

- resource: `PSQL_NAME` from Step 0
- resource-group: `RG` from Step 0
- subscription: `SUBSCRIPTION` from Step 0
- resource-type: `Microsoft.DBforPostgreSQL/flexibleServers`
- metric-namespace: `Microsoft.DBforPostgreSQL/flexibleServers`
- metric names: `cpu_percent,memory_percent,storage_percent,active_connections`
- interval: `PT1H`
- aggregation: `Average` (first query), `Maximum` (second query)

**Verdict thresholds** (B_Standard_B2s — 2 vCores, 4 GB):

| Metric | ✅ Healthy | ⚠️ Warning | 🔴 Critical |
|--------|-----------|-----------|------------|
| CPU (peak) | < 50% | 50–80% | > 80% |
| Memory (peak) | < 70% | 70–85% | > 85% |
| Storage (peak) | < 70% | 70–85% | > 85% |
| Connections | < 80 | 80–100 | > 100 |

---

## Step 8: Container Stability (24h)

Substitute the `LATEST_REVISION` value from Step 0 into the KQL query below.

- table: `ContainerAppSystemLogs_CL`
- query: `ContainerAppSystemLogs_CL | where TimeGenerated > ago(24h) and RevisionName_s == 'LATEST_REVISION_VALUE' | summarize Count=count() by Reason_s, Type_s | order by Count desc`
- hours: 24

Replace `LATEST_REVISION_VALUE` with the actual revision name from Step 0.

**Verdict**: 🔴 if `ContainerCrashing`. ⚠️ if `ReplicaUnhealthy` — check context: a few events alongside `SuccessfulRescale` is normal scale-in/out; sustained events without scaling activity suggest health probe failures.

---

## Step 9: Fired Alerts (24h)

- table: `AzureActivity`
- query: `AzureActivity | where TimeGenerated > ago(24h) | where OperationNameValue has "microsoft.insights/metricalerts" or OperationNameValue has "microsoft.insights/scheduledqueryrules" | where ActivityStatusValue == "Activated" | project TimeGenerated, OperationName, ResourceId | order by TimeGenerated desc`
- hours: 24

**Verdict**: 🔴 if any Sev0/Sev1 alerts fired.

---

## Summary Report

```
## Production Health Report — {date}

### Overall: ✅ Healthy / ⚠️ Warning / 🔴 Critical

**Verdict reasoning**: {1-2 sentence explanation citing specific check(s)}

| # | Check | Status | Details |
|---|-------|--------|---------|
| 1 | Readiness Probe | ✅/🔴 | {status_code}, {X}s response |
| 2 | Availability Tests | ✅/⚠️ | {N} total, {N} failed in 24h |
| 3 | Request Health | ✅/🔴 | P95 {X}ms, {N} 4xx, {N} 5xx |
| 4 | Error Rate Trend | ✅/⚠️ | {stable/rising/falling} over 7d |
| 5 | Exceptions | ✅/⚠️ | {N} unique in 7d, top: {type} |
| 6 | Dependencies | ✅/⚠️ | {type}: {N} calls, {N} failures |
| 7 | Database | ✅/⚠️/🔴 | CPU {X}%, Mem {X}%, Storage {X}%, Conn {X} |
| 8 | Container Stability | ✅/⚠️ | Rev: {rev}, {events} |
| 9 | Fired Alerts | ✅/🔴 | {N} in 24h |

### ⚠️ Items to Watch
- {any warnings — omit if none}

### 🔴 Action Required
- {any critical issues — omit if none}
```

---

## Notes

- **Tool discovery**: Use the Azure MCP monitor tool for all queries. Parameter names may vary across MCP versions — check the tool interface before your first call.
- **Log Analytics table names**: Use `AppRequests`, `AppExceptions`, `AppDependencies` (not the App Insights names `requests`, `exceptions`, `dependencies`).
- **Metrics vs logs**: Step 7 queries Azure Monitor metrics (different from Log Analytics log queries in Steps 2–6, 8–9). These are separate commands in the MCP tool.
- **Parallelization**: Steps 2–7 have no dependencies on each other — run them concurrently to reduce total check time.
