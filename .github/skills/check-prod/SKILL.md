---
name: check-prod
description: Check Azure production health across the API, telemetry, PostgreSQL, dependencies, and alerts. Use for "check prod", "is prod up", "prod status", "health check", "any errors?", or "check Azure".
---

# Check Production

Perform a read-only health assessment of resources in `rg-ltc-dev`. Discover
resource names at runtime; do not rely on generated suffixes. Require an
authenticated Azure CLI session.

Run independent Azure Monitor and Log Analytics queries concurrently after
resource discovery. Cover:

- `/ready` status and response time
- Azure resource health and fired alerts (24h)
- availability failures, request count, 5xx count, and P95 latency (24h)
- exceptions (7d) and error-level traces (24h)
- dependency failures and latency, especially PostgreSQL and `api.github.com`
- PostgreSQL peak CPU, memory, storage, connections, and minimum CPU credits
- Container App peak CPU/memory and current-revision crash or unhealthy events
- console `Traceback`, `FATAL`, `OOMKilled`, or segmentation-fault events
- verification outcomes and OAuth success/failure activity (24h)

Use workspace-mode tables `AppRequests`, `AppExceptions`, `AppTraces`,
`AppDependencies`, `AppAvailabilityResults`, and `AppMetrics`. Container App
tables may use either the `_CL` schema with `_s` columns or the standard schema.

## Verdict

**Critical:** readiness is non-200; any 5xx; unavailable resource; PostgreSQL
dependency failure; OOM/crash; fired Sev1 alert; DB CPU above 80% or credits
below 10.

**Warning:** P95 above 500 ms; failed availability test; recurring exception;
other dependency failure; DB CPU 50-80%, memory/storage 70-85%, or credits
10-30; Container App CPU/memory above 80%; unhealthy replicas without matching
scale events; OAuth callback failures above 50% of observed OAuth callback
outcomes when login activity exists.

Use `auth.login.success` and `auth.callback.*` failure events for OAuth outcomes.
Expected request 401s for missing sessions and 303 login redirects are not OAuth
callback failures or unhandled application errors. Request URL attributes should
use route templates, including router prefixes; `/unmatched` is reserved for
requests without a known route template.

Otherwise report **Healthy**. Missing telemetry is `Unknown`, not healthy.

Return one overall verdict followed by a compact table containing each signal,
its status, observed value, and time window. Put actionable critical findings
first and distinguish application failures from Azure telemetry-query failures.
