---
name: check-prod
description: Check Azure production health - app status, errors, latency, database, dependencies. Use when user says "check prod", "how's prod", "hows prod doing", "is prod up", "prod status", "health check", "any errors?", "how's the app doing?", or "check Azure".
---

# Production Health Check

This skill is a **router** for production health checks. Prefer Azure skills and MCP tools over hand-written CLI commands. Keep the check read-only and report one clear verdict.

## Production Scope

- Subscription: use the active/default Azure subscription unless the user specifies another one.
- Resource group: `rg-ltc-dev`
- Expected production resources:
  - Container App for the FastAPI API
  - Azure Container Apps environment
  - Azure Database for PostgreSQL Flexible Server
  - Log Analytics workspace
  - Application Insights component
  - Azure Container Registry

## Skill Routing

Use these skills in this order:

| Need | Preferred skill | Purpose |
|---|---|---|
| Discover Azure resources and confirm IDs | `azure-resource-lookup` | Find the Container App, Log Analytics workspace, PostgreSQL server, App Insights component, and related resource IDs. |
| Read Container App inventory/status | `azure-containerapps` | Confirm the Container App exists, provisioning state is healthy, and the managed environment is present. |
| Check Azure platform health | `azure-resourcehealth` | Check availability status for supported resources in `rg-ltc-dev`, especially PostgreSQL, Log Analytics, and alert resources. |
| Query logs and metrics | `azure-monitor` | Check request health, exceptions, traces, dependencies, availability tests, Container App logs, alerts, business metrics, and resource metrics. |
| Interpret app health and Azure-side issues | `azure-diagnostics` | Use for diagnostic guidance and correlation across resource health, Container App telemetry, logs, metrics, alerts, dependency failures, and likely root cause. |
| Investigate cost or spend anomalies | `azure-cost` | Use only if the user asks about spend, cost spikes, budgets, or waste. |
| Investigate security or compliance posture | `azure-compliance` | Use only if the user asks for security/compliance findings as part of the health check. |
| Visualize topology | `azure-resource-visualizer` | Use only if the user asks for an architecture/resource relationship view. |

Do **not** use this skill to deploy, modify, restart, scale, rotate secrets, change firewall rules, or reset data.

Do **not** use `azure-applens` for this Container App health check. AppLens currently does not support `Microsoft.App/containerApps` in this environment, so it adds noise instead of useful evidence. If AppLens gains Container Apps support later, treat it as optional enrichment only, not a required check.

## Health Dimensions

Ask the routed skills/tools for evidence across these dimensions:

1. **Availability** - live readiness/health status, resource health, availability tests, fired alerts.
2. **Request health** - request volume, P95 latency, 4xx/5xx counts, failed-request trend.
3. **Application errors** - unhandled exceptions, ERROR-level traces, crash indicators, OOM, restarts.
4. **Dependencies** - PostgreSQL dependency health, GitHub/API dependency health, outbound failure counts and latency.
5. **Database health** - PostgreSQL CPU, memory, storage, active connections, burst credits, and sustained pressure.
6. **Container App health** - current revision, provisioning state, replicas, CPU/memory utilization, scale events, probe failures.
7. **Business signals** - auth login result mix, verification attempts, step completions, user deletions, or other custom metrics when available.

## Verdict Rules

Evaluate top-down; first matching verdict wins.

### Critical

Use **Critical** for active or customer-impacting failures, including:

- Readiness/health endpoint is unavailable or non-200.
- Any 5xx errors in the recent production window.
- Fired Sev0/Sev1 alert in the last 24 hours.
- Container crashing, OOMKilled, restart loop, or current revision not ready.
- PostgreSQL dependency failures, sustained DB CPU over 80%, DB memory/storage over 85%, or CPU credits below 10.
- GitHub/API dependency failures above 20 in 24 hours.
- `init.failed` or equivalent app startup failure logs.

Do not mark transient Container App startup CPU as Critical if it occurs only during deploy/scale-out and there is no customer impact.

### Warning

Use **Warning** for degraded but non-critical signals, including:

- P95 latency over 500 ms.
- Failed availability tests.
- Recurring exceptions or more than 10 ERROR-level traces in 24 hours.
- PostgreSQL CPU 50-80%, memory/storage 70-85%, CPU credits 10-30, or active connections approaching the SKU limit.
- Container App CPU/memory pressure that is sustained or correlated with slow/failed requests.
- `ReplicaUnhealthy` without matching deploy, scale-out, or scale-in events.
- Error-rate spike over 2x weekly average or a 3+ day rising trend.
- Auth failure rate over 50%.

Treat probe failures during revision rollout or scale transitions as a watch item unless they persist after the transition.

### Healthy

Use **Healthy** when none of the Critical or Warning conditions apply.

## Investigation Guidance

- Start broad with resource discovery and health, then narrow only if a signal is unhealthy.
- Correlate symptoms before assigning severity: compare metrics with request failures, logs, dependency telemetry, scale events, revision changes, and alerts.
- Prefer sustained conditions over single-point metric spikes. A one-minute CPU spike during deploy or scale-out is usually not customer-impacting without matching latency, 5xx, crash, or alert evidence.
- Keep checks read-only. If remediation is needed, report it as an action item instead of making changes.
- If an Azure skill or MCP tool cannot access a signal, state that the signal was unavailable and continue with the remaining evidence.

## Summary Report

Return a concise report in this shape:

```markdown
## Production Health Report - {date}

### Overall: Healthy / Warning / Critical

**Verdict reasoning**: {1-2 sentences citing the strongest evidence}

| Check | Status | Details |
|---|---|---|
| Resource discovery | Healthy/Warning/Critical | {resources found, missing, or inaccessible} |
| Availability | Healthy/Warning/Critical | {readiness, availability tests, resource health} |
| Requests | Healthy/Warning/Critical | {P95 latency, volume, 4xx, 5xx, error trend} |
| Errors | Healthy/Warning/Critical | {exceptions, traces, crashes, restarts} |
| Dependencies | Healthy/Warning/Critical | {PostgreSQL, GitHub/API, other dependencies} |
| Database | Healthy/Warning/Critical | {CPU, memory, storage, connections, credits} |
| Container App | Healthy/Warning/Critical | {revision, replicas, CPU/memory, scale/probe events} |
| Alerts | Healthy/Warning/Critical | {fired alerts and severities} |
| Business signals | Healthy/Warning/Critical | {auth, verification, completion, deletion metrics} |

### Items to Watch
- {omit this section if none}

### Action Required
- {omit this section if none}
```
