---
name: check-prod
description: Check Azure production health app status, errors, latency, database, dependencies. Use when user says check prod, how's prod, hows prod doing.
---

# Production Health Check

14 read-only checks. One verdict. Data collection is automated by a script;
your job is to interpret the results and produce the report.

## How it works

1. A single script gathers every signal in parallel and prints one JSON object.
2. You read that JSON, apply the **Verdict Logic** below, and fill in the
   **Summary Report** template.

The script collects data only. All judgment (thresholds, trends, severity)
stays here so you can reason over the raw numbers.

## Prerequisites

- Azure CLI logged in (`az login`). The script exits with code 2 and a clear
  message if not.
- `curl` and `jq` available (the script checks and exits 3 if missing).

## Step 1: Run the collector

```bash
bash scripts/check-prod.sh > /tmp/check-prod.json
```

- Add `--discover-only` to just confirm resource discovery without querying.
- Exit codes: `0` data collected, `2` not authenticated, `3` missing tool,
  `4` resources not found in `rg-ltc-dev`.

The output shape:

```json
{
  "generated": "<UTC timestamp>",
  "discovery": { "containerApp": "...", "workspace": "...", "postgres": "...", "containerAppDetail": { "fqdn": "...", "latestRevision": "..." } },
  "checks": {
    "1_readiness": { "status": 200, "response_time": 0.27 },
    "2_resource_health": [ ... ],
    "3_availability_tests": [ ... ],
    "4_request_health": [ ... ],
    "5_error_rate_trend": [ ... ],
    "6_exceptions": [ ... ],
    "6_error_traces": [ ... ],
    "7_dependencies": [ ... ],
    "8_db_avg": { ... }, "8_db_peak": { ... }, "8_db_credits": { ... },
    "9_container_app": { ... },
    "10_container_stability": [ ... ],
    "11_fired_alerts": [ ... ],
    "12_business_metrics": [ ... ], "12_auth_ratio": [ ... ],
    "13_console_errors": [ ... ]
  }
}
```

Log-analytics checks (`3`, `4`, `5`, `6`, `7`, `10`, `11`, `12`, `13`) return an
array of row objects. Metric checks (`8`, `9`) return the raw
`az monitor metrics list` object; read peaks from
`.value[].timeseries[0].data[].maximum` (or `.average` / `.minimum`).

## Step 2: Apply the verdict logic

Evaluated top-down, first match wins:

**🔴 Critical**: ANY of: readiness probe non-200, any 5xx in 24h, DB CPU > 80%
sustained, DB CPU credits < 10, fired Sev0/Sev1 alerts in 24h,
`ContainerCrashing` or `OOMKilled` on current revision, any `init.failed` logs
in 24h, GitHub API failures > 20 in 24h, console OOMKilled or Segfault.

**⚠️ Warning**: ANY of: P95 latency > 500ms, DB CPU 50–80% peak or Memory
70–85% or Storage 70–85% or CPU credits 10–30, any failed availability tests in
24h, non-zero unhandled exceptions in 7d, active connections > 80 (B1ms max
100), `ReplicaUnhealthy` without matching scale events, error rate spike
(single day > 2× weekly average) or rising trend (3+ consecutive days
increasing), Container App CPU > 80% or Memory > 80%, ERROR-level AppTraces > 10
in 24h, auth failure rate > 50% in 24h, recurring console Tracebacks (> 5 in
24h).

**✅ Healthy**: none of the above.

### Per-check reference

| # | JSON key | What it measures | Verdict |
|---|----------|------------------|---------|
| 1 | `1_readiness` | `/ready` live probe | 🔴 if status non-200; ⚠️ if response_time > 2s |
| 2 | `2_resource_health` | Azure platform health | 🔴 if any `Unavailable`; ⚠️ if `Degraded` |
| 3 | `3_availability_tests` | Synthetic tests 24h (~288/day) | ⚠️ if any `Failed` > 0 |
| 4 | `4_request_health` | P95, 4xx, 5xx 24h | 🔴 if `Err5xx` > 0; ⚠️ if `P95` > 500ms (4xx expected) |
| 5 | `5_error_rate_trend` | Daily error rate 7d | ⚠️ if rising 3+ days or single day > 2× the 7-day average |
| 6 | `6_exceptions`, `6_error_traces` | Unhandled exceptions 7d, ERROR traces 24h | ⚠️ if recurring exceptions, or error traces > 10 in 24h |
| 7 | `7_dependencies` | PostgreSQL, GitHub API, other outbound 24h | 🔴 if PostgreSQL fail > 0 or GitHub fail > 20; ⚠️ any other fail > 0 |
| 8 | `8_db_avg`, `8_db_peak`, `8_db_credits` | DB metrics 24h | See DB threshold table below |
| 9 | `9_container_app` | Container CPU/memory 24h | See container threshold table below |
| 10 | `10_container_stability` | System log events on current revision | 🔴 if `ContainerCrashing`/`OOMKilled`; ⚠️ if `ReplicaUnhealthy` without scaling |
| 11 | `11_fired_alerts` | Activated alerts 24h | 🔴 if Sev0/Sev1; ⚠️ if Sev2 (see alert map) |
| 12 | `12_business_metrics`, `12_auth_ratio` | Domain counters + auth success/fail | ⚠️ if auth failure rate > 50% |
| 13 | `13_console_errors` | stdout/stderr crash indicators 24h | 🔴 if OOMKilled/Segfault; ⚠️ if Tracebacks > 5 |

**DB thresholds** (B_Standard_B1ms: 1 vCore, 2 GB, burstable):

| Metric | ✅ Healthy | ⚠️ Warning | 🔴 Critical |
|--------|-----------|-----------|------------|
| CPU (peak) | < 50% | 50–80% | > 80% |
| Memory (peak) | < 70% | 70–85% | > 85% |
| Storage (peak) | < 70% | 70–85% | > 85% |
| Connections (peak) | < 80 | 80–100 | > 100 |
| CPU credits remaining (min) | > 30 | 10–30 | < 10 |

**Container App thresholds** (0.5 CPU / 1 Gi allocated):

| Metric | ✅ Healthy | ⚠️ Warning | 🔴 Critical |
|--------|-----------|-----------|------------|
| CPU (UsageNanoCores peak) | < 300M | 300M–400M | > 400M |
| Memory (WorkingSetBytes peak) | < 750Mi | 750Mi–860Mi | > 860Mi |

**Alert severity map** (match against `AlertName` in `11_fired_alerts`):

- **Sev0**: `alert-ltc-availability-*` (app unreachable)
- **Sev1**: `alert-ltc-api-5xx-*`, `alert-ltc-api-restarts-*`, `alert-ltc-db-connections-*`, `alert-ltc-db-credits-*`, `alert-ltc-init-failed-*`
- **Sev2**: `alert-ltc-api-cpu-*`, `alert-ltc-api-memory-*`, `alert-ltc-api-latency-*`, `alert-ltc-api-4xx-*`, `alert-ltc-db-storage-*`, `alert-ltc-db-cpu-*`

## Step 3: Summary Report

```
## Production Health Report: {date}

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
- {any warnings, omit if none}

### 🔴 Action Required
- {any critical issues, omit if none}
```

## Gotchas

- **No MCP dependency.** Uses only `az` CLI (needs `az login`) plus `curl`/`jq`.
  Works without the azure-skills plugin.
- **Workspace `-w` value.** The script passes the workspace **name** to
  `az monitor log-analytics query`, matching the proven-working form for this
  project. If queries return empty in an environment where you expect data,
  check that the `az monitor` module and `log-analytics` extension load
  correctly (`az monitor log-analytics query --help`).
- **Container log table names vary.** System and console logs live in either a
  `*_CL` custom table (with `_s`/`_g` column suffixes) or a standard table. The
  script tries the `*_CL` table first and falls back automatically, so checks
  10 and 13 work under either schema.
- **Metrics vs logs are different commands.** Checks 8–9 use
  `az monitor metrics list`; the rest use `az monitor log-analytics query`. The
  script handles both; just read the two shapes differently (see Step 1).
- **Hostname / resource names can change** if infrastructure is recreated. The
  script rediscovers everything by resource type each run, so you never
  hard-code names.
- **Infrastructure tier.** PostgreSQL is B_Standard_B1ms (1 vCore, 2 GB,
  burstable). Container App is 0.5 CPU / 1 Gi, 1–2 replicas. Thresholds above
  are tuned for these SKUs.

## Available scripts

- **`scripts/check-prod.sh`**: collects all 14 read-only health signals in
  parallel and prints one JSON object. Pass `--discover-only` to just resolve
  resource names.
