# Research: Azure MCP Server vs Azure CLI for prod-health-check Skill

## Question

The `prod-health-check` skill currently uses Azure CLI (`az`) commands run via terminal to check production health. Should we replace it with the Azure MCP Server tools, the GitHub Copilot for Azure extension, or keep Azure CLI?

---

## How the Current System Works

### Skill file: [.github/skills/prod-health-check/SKILL.md](.github/skills/prod-health-check/SKILL.md)

The skill is a 600-line markdown file that instructs the Copilot agent to run **~30 distinct `az` CLI commands** via terminal across 11 steps. It covers:

| Step | What it checks | Azure CLI commands used |
|------|---------------|----------------------|
| 0 | Resource discovery | `az account set`, `az resource list` (4 queries for CA, APPI, PSQL, LOG) |
| 1 | Container App status | `az containerapp show`, `az containerapp replica list` |
| 2 | Request volume & latency | `az monitor app-insights query` (3 KQL queries) |
| 3 | HTTP errors (4xx/5xx) | `az monitor app-insights query` (3 KQL queries) |
| 4 | Exceptions & error traces | `az monitor app-insights query` (2 KQL queries) |
| 5 | Container system events | `az monitor log-analytics query` (4+ KQL queries, revision-aware) |
| 6 | Database metrics | `az monitor metrics list` (4 queries: CPU, memory, storage, connections) |
| 7 | App CPU & memory | `az monitor app-insights query` (1 KQL query) |
| 8 | Dependency health | `az monitor app-insights query` (2 KQL queries) |
| 8b | Telemetry richness | `az monitor app-insights query` (5 KQL queries) |
| 9 | Console logs | `az containerapp logs show` |
| 10 | Alert status | `az monitor metrics alert list`, `az monitor scheduled-query list`, `az monitor activity-log list` |
| 11 | DB user stats | `az postgres flexible-server firewall-rule create`, `az postgres flexible-server execute` |

### Key characteristics of the current approach

1. **Shell variable chaining**: Step 0 discovers resource names and stores them in shell variables (`$CA_NAME`, `$APPI_NAME`, etc.) that all subsequent commands reference
2. **Complex `--query` JMESPath projections**: Most commands use `--query` to reshape JSON output (e.g., `--query "{provisioningState:..., runningStatus:...}"`)
3. **Custom KQL queries**: Steps 2-5, 7-8b use full KQL query strings embedded in bash
4. **Conditional logic**: Step 5 checks for `ReplicaUnhealthy` events and only runs deeper log pulls if found
5. **Cross-platform date handling**: macOS `date -v-24H` vs Linux `date --date='24 hours ago'`
6. **Firewall mutation**: Step 11 creates a PostgreSQL firewall rule (only step that mutates state)

---

## Azure MCP Server Tools — Full Capability Inventory

### Available MCP tools relevant to health-check

I inventoried every Azure MCP tool available in the current VS Code environment. Here's what maps to each health-check step:

| Health-Check Step | Azure CLI Command | MCP Tool Equivalent | Coverage |
|-------------------|-------------------|---------------------|----------|
| **Step 0: Resource discovery** | `az resource list` | `group_list` (resource groups only) | ❌ **No generic resource list** |
| **Step 1: Container App status** | `az containerapp show`, `az containerapp replica list` | Container Apps namespace exists but **list-only** (no show/replicas/logs) | ❌ **Insufficient** |
| **Step 2: Request volume (App Insights KQL)** | `az monitor app-insights query` | `monitor_workspace_log_query` (KQL against Log Analytics) | ⚠️ **Partial** — queries Log Analytics workspace, not App Insights directly |
| **Step 3: HTTP errors (App Insights KQL)** | `az monitor app-insights query` | `monitor_workspace_log_query` | ⚠️ **Partial** — same caveat |
| **Step 4: Exceptions (App Insights KQL)** | `az monitor app-insights query` | `monitor_workspace_log_query` | ⚠️ **Partial** |
| **Step 5: Container system events** | `az monitor log-analytics query` | `monitor_workspace_log_query` | ✅ **Direct match** — both query Log Analytics |
| **Step 6: DB metrics** | `az monitor metrics list` | `monitor_metrics_query` | ✅ **Direct match** |
| **Step 7: App CPU/memory (perf counters)** | `az monitor app-insights query` | `monitor_workspace_log_query` | ⚠️ **Partial** |
| **Step 8: Dependency health** | `az monitor app-insights query` | `monitor_workspace_log_query` | ⚠️ **Partial** |
| **Step 9: Console logs** | `az containerapp logs show` | None | ❌ **No equivalent** |
| **Step 10: Alert status** | `az monitor metrics alert list`, `az monitor activity-log list` | `monitor_activitylog_list` (activity logs only) | ⚠️ **Partial** — no alert config listing |
| **Step 11: DB queries** | `az postgres flexible-server execute` | `postgres_database_query` | ✅ **Direct match** |
| **Step 11: DB firewall** | `az postgres flexible-server firewall-rule create` | None | ❌ **No equivalent** |
| **Resource health** | N/A (not in current skill) | `resourcehealth_availability-status_list` | ✅ **Bonus** — new capability |
| **Service health events** | N/A (not in current skill) | `resourcehealth_health-events_list` | ✅ **Bonus** — new capability |
| **App Lens diagnostics** | N/A (not in current skill) | `applens_resource_diagnose` | ✅ **Bonus** — new capability |

### MCP tool details (from actual tool schemas)

**`monitor_workspace_log_query`** — The closest thing to `az monitor app-insights query`:
- Requires: `resource-group`, `workspace` (name or GUID), `table`, `query` (KQL)
- Optional: `hours`, `limit`
- **Critical difference**: This queries Log Analytics workspace tables, not Application Insights directly. App Insights data flows to Log Analytics (if workspace-based App Insights is configured), so KQL queries *can* work — but the table names may differ (`AppRequests` vs `requests`, `AppExceptions` vs `exceptions`, `AppTraces` vs `traces`, `AppDependencies` vs `dependencies`).

**`monitor_metrics_query`** — Direct replacement for `az monitor metrics list`:
- Requires: `resource` (name), `metric-names` (comma-separated), `metric-namespace`
- Optional: `resource-group`, `resource-type`, `start-time`, `end-time`, `interval`, `aggregation`, `max-buckets`
- **Good fit**: DB metrics (CPU%, memory%, storage%, active_connections) map directly

**`monitor_activitylog_list`** — Partial replacement for alert checking:
- Requires: `resource-name`
- Optional: `resource-group`, `resource-type`, `hours`, `event-level`, `top`
- **Missing**: Cannot list configured metric alerts or scheduled query rules

**`postgres_database_query`** — Replacement for `az postgres flexible-server execute`:
- Requires: `resource-group`, `user`, `server`, `database`, `query`
- **Advantage**: No need for manual Entra token acquisition — MCP handles auth
- **Advantage**: No need for firewall rule creation — MCP server connects differently
- **Unknown**: Whether it requires the `rdbms-connect` extension or handles auth via managed identity/DefaultAzureCredential

**`resourcehealth_availability-status_list`** — New capability:
- Optional: `resource-group`
- Lists health status for all resources in the resource group — useful as a quick triage

**`applens_resource_diagnose`** — New capability:
- Requires: `resource-group`, `question`, `resource`, `resource-type`
- AI-powered diagnostics — ask natural language questions about resource health

### Tools that DO NOT exist in Azure MCP

These are critical gaps (verified against [azmcp-commands.md](https://github.com/microsoft/mcp/blob/main/servers/Azure.Mcp.Server/docs/azmcp-commands.md) — 2,898 lines, 144 KB):

1. **Container Apps: list-only** — The README lists a "Container Apps" namespace with prompts "List the container apps in my subscription" and "Show me the container apps in my 'my-resource-group' resource group", but the commands doc has **zero Container Apps CLI commands**. This suggests a very thin wrapper — likely just listing, no `show` (details/provisioning state), no `replica list`, no `logs show`. Cannot check running status, revision, replica health, or console logs.
2. **No Application Insights direct query** — Only one tool (`applicationinsights_recommendation_list`) for code optimization recommendations, not KQL queries. All App Insights KQL must go through `monitor_workspace_log_query` against Log Analytics.
3. **No generic resource listing/discovery** — `group_list` lists resource groups, but there is no `az resource list` equivalent to discover resources by type within a group.
4. **No alert configuration listing** — Cannot list configured metric alerts or scheduled query rules.
5. **No PostgreSQL firewall rule management** — Cannot create/manage PostgreSQL firewall rules (though `postgres_database_query` may handle auth via DefaultAzureCredential without needing firewall rules).
6. **App Service is also thin** — README shows "List websites", "Get details", but the commands doc only has `appservice database add`. Similar incomplete pattern.

### Namespace filtering and server modes (important for context usage)

The README documents several server modes that affect context window consumption:

- **Namespace mode (default)**: Collapses all tools per namespace into one meta-tool. E.g., all `monitor` operations become one `monitor` tool with internal routing. Designed to stay under VS Code's 128-tool limit.
- **Consolidated mode**: Curated tool groups organized by workflow (e.g., `get_azure_databases_details`). Better for AI agents — reduces decision complexity.
- **Namespace filtering**: `--namespace monitor --namespace postgres` loads only those namespaces. This is the recommended approach for context efficiency.
- **Tool filtering**: `--tool azmcp_monitor_metrics_query --tool azmcp_postgres_database_query` for finest granularity.
- **`--read-only` flag**: Filters to only read-only tools — great for health checks.

These modes partially address the context bloat concern, but you must configure them explicitly.

---

## GitHub Copilot for Azure Extension

The Copilot for Azure VS Code extension (`@azure` chat participant) is a separate product from the MCP server. Key characteristics:

- **Conversational interface** — uses `@azure` in chat, not tool calls
- **Capabilities**: Resource Graph queries, service health, Azure Monitor metrics/logs, deploy guidance
- **Limitations**: Not programmable from a skill file — it's a chat participant, not a tool the agent can call programmatically
- **Not composable**: Cannot be chained in a scripted health-check workflow the way CLI commands or MCP tools can

**Verdict**: Not a viable replacement. The skill needs programmable, scriptable tool calls — not a chat participant.

---

## Comparison: Azure CLI vs Azure MCP for This Skill

### Coverage Summary

| Capability | Azure CLI | Azure MCP |
|-----------|-----------|-----------|
| Resource discovery (`az resource list`) | ✅ | ❌ |
| Container App status/replicas/logs | ✅ | ❌ |
| Application Insights KQL queries | ✅ (direct) | ⚠️ (indirect via Log Analytics) |
| Log Analytics KQL queries | ✅ | ✅ |
| Azure Monitor metrics | ✅ | ✅ |
| Activity logs | ✅ | ✅ |
| Alert config listing | ✅ | ❌ |
| PostgreSQL queries | ✅ | ✅ |
| PostgreSQL firewall rules | ✅ | ❌ |
| Resource health status | ❌ (not in skill) | ✅ (bonus) |
| Service health events | ❌ (not in skill) | ✅ (bonus) |
| App Lens diagnostics | ❌ (not in skill) | ✅ (bonus) |

**Azure CLI covers 12/12 steps. Azure MCP covers ~5/12 steps fully, ~4/12 partially.**

### Context Window / Token Usage

This is where MCP gets *worse*, not better:

**Azure CLI approach (current)**:
- The skill file is ~600 lines of markdown (~3,500 tokens)
- Each `az` command produces plain-text/JSON output that **goes into context** — typically 200–2,000 tokens per command
- The `run_in_terminal` tool is one generic tool already loaded — no additional tool schema cost
- Total for a lean 9-step health check: ~3,500 (skill) + ~5,000 (command outputs) ≈ **~8,500 tokens**
- The agent has full control over `--query` JMESPath to minimize output size

**Azure MCP approach**:
- Tool definitions are loaded into context when MCP server starts. The Azure MCP server exposes **42+ service areas** with dozens of commands each
- Each tool definition is ~500–1,500 tokens (parameters, descriptions, schema)
- **Loading just the `monitor` namespace adds ~6,000 tokens** of tool definitions to context
- Loading `monitor` + `postgres` + `resourcehealth` + `applens` ≈ **~15,000 tokens** just for tool schemas
- **Mitigation**: Namespace filtering (`--namespace monitor --namespace postgres`) and `--read-only` flag can reduce this. Consolidated mode groups related operations. Tool-level filtering (`--tool azmcp_monitor_metrics_query`) gives finest control.
- HN user report: *"A consultant started recommending the Azure DevOps MCP and my context window would start around 25% full"* ([source](https://news.ycombinator.com/item?id=46334424))
- Blog post: *"Connect five MCP servers and your agent loads 100+ tool definitions before writing a single line of code. Five servers might consume 50,000+ tokens - 40% of your context window"* ([source](https://dev.to/aws-builders/why-an-aws-architect-built-azure-powers-for-kiro-and-what-i-learned-2dg4))

**Namespace filtering mitigates this partially** — Azure MCP supports `--namespace` flags to load only specific modules. But even filtered, the tool schemas are verbose (every parameter includes retry config, tenant, auth-method boilerplate).

### Speed

**Azure CLI**:
- Each `az` command takes 2–8 seconds (cold start + HTTP round-trip + JMESPath)
- `az monitor app-insights query` is particularly slow (3–6 seconds)
- But commands can be chained with `&&` and the shell persists state between calls
- Total wall-clock for full health check: ~2–4 minutes

**Azure MCP**:
- Each MCP tool call is an LLM→MCP Server→Azure API round-trip
- The MCP server itself adds an intermediary hop
- MCP calls cannot be parallelized by the agent (sequential tool calls)
- No benchmarks available comparing speed, but additional hop = likely slower per call
- **Plus**: Each MCP call consumes tool-call tokens (input schema + response)

### Reliability & Precision

**Azure CLI** (current approach):
- Commands are **exact and reproducible** — the skill specifies the precise `az` command, `--query` projection, and output format
- No LLM interpretation between intent and execution — the agent copy-pastes the command
- JMESPath `--query` controls exactly what data comes back
- Cross-platform date handling is explicit (macOS vs Linux)
- Shell variable chaining (`$CA_NAME`) enables complex multi-step workflows

**Azure MCP**:
- MCP tools are **higher-level abstractions** — the agent describes intent, the MCP server interprets it
- Less control over exact query parameters and output shape
- `monitor_workspace_log_query` requires the agent to know the correct Log Analytics table name (`AppRequests` vs `requests`)
- No way to chain results between MCP calls via variables — each call is independent
- **App Insights indirect querying risk**: If the workspace-based App Insights is configured differently, table names (`requests` vs `AppRequests`) could break queries silently

### Composability

**Azure CLI**:
- Shell variables, conditionals (`if`), pipes, and command chaining give full programmatic control
- Step 5's conditional logic (check for `ReplicaUnhealthy` → conditionally pull console logs) is natural in bash
- The skill file IS the program — deterministic, auditable, version-controlled

**Azure MCP**:
- Each tool call is isolated — no variable passing between calls
- Conditional logic must be handled by the LLM agent (non-deterministic)
- The agent must remember outputs from prior MCP calls and use them in subsequent calls — prone to context window pressure and hallucination

---

## What Azure MCP *Would* Be Good For

Despite the gaps, Azure MCP offers three genuinely useful tools that the current skill doesn't have:

### 1. `resourcehealth_availability-status_list`
Quick triage of all resources in the resource group — a single call replacing what currently requires checking each resource individually.

```
# Could add as Step 0.5 in the skill
Use MCP tool: resourcehealth_availability-status_list
  resource-group: rg-ltc-dev
```

### 2. `resourcehealth_health-events_list`
Service health events (outages, planned maintenance) — currently not checked at all.

### 3. `applens_resource_diagnose`
AI-powered diagnostics — could be used as a follow-up when the health check finds issues:
```
Use MCP tool: applens_resource_diagnose
  resource-group: rg-ltc-dev
  resource: <container-app-name>
  resource-type: Microsoft.App/containerApps
  question: "Why are there ReplicaUnhealthy events in the last 24 hours?"
```

### 4. `postgres_database_query`
Direct DB query without firewall rule creation or manual token acquisition. This is genuinely better than the current approach for Step 11 — eliminates the `curl ifconfig.me` → firewall rule → token acquisition dance.

---

## Potential Gotchas

### 1. App Insights Table Name Divergence
The MCP `monitor_workspace_log_query` queries Log Analytics, not App Insights directly. If using workspace-based Application Insights, the table names in Log Analytics are different:

| App Insights table | Log Analytics table |
|-------------------|-------------------|
| `requests` | `AppRequests` |
| `exceptions` | `AppExceptions` |
| `traces` | `AppTraces` |
| `dependencies` | `AppDependencies` |
| `performanceCounters` | `AppPerformanceCounters` |

All the KQL queries in the current skill use the App Insights table names. Migrating to MCP would require rewriting every KQL query.

### 2. Container Apps Support Is List-Only
The Azure MCP server has a Container Apps namespace, but per the [commands doc](https://github.com/microsoft/mcp/blob/main/servers/Azure.Mcp.Server/docs/azmcp-commands.md) it only supports listing apps — no `show` (provisioning state, running status, FQDN), no `replica list`, no `logs show`. Steps 1 (status/replicas) and 9 (console logs) have **effectively zero useful MCP coverage** for health checking. These are arguably the most important operational checks.

### 3. Tool Definition Bloat
Each Azure MCP tool schema includes ~10 boilerplate parameters (tenant, auth-method, 5 retry parameters, subscription). These add ~300 tokens per tool. With 15+ tools loaded, that's 4,500+ tokens of boilerplate alone.

### 4. Hybrid Approach Complexity
A hybrid (MCP for some steps, CLI for others) would require the skill to explain two different execution models to the agent, increasing skill complexity and confusion risk. The agent would need to know when to use `run_in_terminal` vs MCP tool calls.

### 5. MCP Server Startup Cost
The Azure MCP server runs as a subprocess. First tool call triggers server startup, which adds latency. Subsequent calls are faster, but there's a cold-start penalty.

---

## Recommendation Matrix

| Factor | Keep Azure CLI | Switch to MCP | Hybrid |
|--------|---------------|---------------|--------|
| **Coverage** | ✅ 12/12 steps | ❌ 5/12 steps | ⚠️ Complex |
| **Context efficiency** | ✅ ~18.5K tokens | ❌ ~30K+ tokens | ⚠️ Both costs |
| **Speed** | ✅ Direct API calls | ⚠️ Extra hop | ⚠️ Mixed |
| **Reliability** | ✅ Deterministic | ⚠️ LLM-interpreted | ⚠️ Mixed |
| **Composability** | ✅ Shell variables | ❌ No chaining | ⚠️ Complex |
| **Auth simplicity** | ⚠️ Manual token mgmt | ✅ DefaultAzureCredential | ✅ Best of both |
| **DB queries** | ⚠️ Firewall + token dance | ✅ Direct via MCP | ✅ Use MCP |
| **Resource health** | ❌ Not available | ✅ New capability | ✅ Use MCP |
| **Maintenance** | ✅ Stable CLI API | ⚠️ MCP server evolving | ⚠️ Two systems |

---

## Verdict

**Keep Azure CLI as the primary mechanism.** The MCP server has critical coverage gaps (no Container Apps, no App Insights direct query, no resource discovery) and worse context efficiency. The current skill is well-tuned, deterministic, and covers 100% of the health-check surface.

**Consider adding 2-3 MCP tools as supplements** (not replacements):

1. **`postgres_database_query`** for Step 11 — eliminates firewall + token complexity
2. **`resourcehealth_availability-status_list`** as a new Step 0.5 — quick triage
3. **`applens_resource_diagnose`** for Mode B (deeper investigation) — AI-powered follow-up

**Do not use** the GitHub Copilot for Azure extension — it's a chat participant, not a programmable tool.

**Re-evaluate when** Azure MCP adds Container Apps and Application Insights namespaces (tracked: [Azure MCP tools page](https://learn.microsoft.com/en-us/azure/developer/azure-mcp-server/tools/)).

---

## Live Test Results (2026-02-22)

Both implementations were executed against the live `rg-ltc-dev` deployment. The lean health check covers 9 crucial steps (trimmed from the original 11 — see Skill Audit below).

### Skill Audit: What's Crucial vs Not

| Section | Verdict | Rationale |
|---------|---------|-----------|
| Preamble (modes, when-to-use) | Not crucial | Agent routing meta — 80 lines that don't run checks |
| Prerequisites | Not crucial | If `az` isn't logged in, the first command fails anyway |
| **Step 0: Resource Discovery** | **Crucial** | Everything else depends on `$CA_NAME`, `$APPI_NAME`, etc. |
| **Step 1: Container App Status** | **Crucial** | "Is the app running?" — #1 question |
| **Step 2: Request Volume** | **Crucial (but bloated)** | 5 queries for one concept. The 24h single-row summary is sufficient. |
| **Step 3: HTTP Errors** | **Crucial (but bloated)** | 3 queries. The 24h status-code-counts query is sufficient. |
| **Step 4: Exceptions** | **Crucial** | Both exception and warning trace queries needed |
| **Step 5: Container Events** | **Partly crucial** | Summary + current-revision filter = crucial. The conditional ReplicaUnhealthy deep-dive is Mode B. |
| **Step 6: DB Metrics** | **Crucial (but bloated)** | 4 queries → merge to 2 (current avg + peak) |
| Step 7: App CPU/Memory | Not crucial | Duplicates DB metrics + container metrics; rarely the bottleneck |
| **Step 8: Dependencies** | **Crucial** | DB and external API failure detection |
| Step 8b: Telemetry Richness | Not crucial | Observability audit, not health check — 5 queries to verify log structure |
| **Step 9: Console Logs** | **Crucial** | Instant signal on crashes/errors |
| **Step 10: Alerts** | Marginally crucial | Other checks already surface what alerts catch. Keep fired-alerts only. |
| Step 11: DB User Stats | Not crucial for health | Product metrics, not operational. Requires firewall mutation. |
| Notes / Cross-platform dates | Not crucial | Agent noise |

**The current skill runs ~30 commands. A tight health check needs ~12.**

### Side-by-Side: Data Comparison

#### Step 1: Container App Status

| | CLI | MCP |
|---|---|---|
| Data | `provisioningState: Succeeded`, `runningStatus: Running`, revision `0000149`, min=1/max=2 replicas, FQDN | **Cannot get this.** No Container App `show` in MCP. `resourcehealth_availability-status_list` shows "Available" but no provisioning state, replicas, or revision. |
| Time | 1.0s | N/A |

#### Step 2: Request Volume (24h)

| | CLI | MCP |
|---|---|---|
| Data | total=1,008, failed=55, p95=19ms | total=21,544, failed=1,288, p95=17.7ms |
| Match? | **No** — different data sources. CLI queries App Insights `requests` table directly. MCP queries Log Analytics `AppRequests` table. Log Analytics accumulates wider ingestion window. Ratios similar (~5.5% failure). |
| Time | 1.8s | ~3s |

#### Step 3: HTTP Errors (24h)

| | CLI | MCP |
|---|---|---|
| Data | 404=43, 405=11, 403=1 | 404=1,016, 405=264, 403=7, 401=1 |
| Match? | **Same pattern, different counts** — App Insights vs Log Analytics windows. Same relative distribution. |
| Time | 3.0s | ~3s |

#### Step 4: Exceptions (7d)

| | CLI | MCP |
|---|---|---|
| Data | **Empty (0 exceptions)** | OAuthError=87, MismatchingStateError=65, ConnectionRefusedError=54, TimeoutError=6, ProgrammingError=4, etc. (221+ total) |
| Match? | **No — MCP was better here.** `AppExceptions` in Log Analytics captured exceptions that App Insights `exceptions` table query returned zero for. |
| Time | 1.0s | ~3s |

#### Step 5: Container System Events (24h)

| | CLI | MCP |
|---|---|---|
| Data | ContainerCrashing=31, RevisionUpdate=27, ReplicaUnhealthy=19, etc. | Identical: ContainerCrashing=31, RevisionUpdate=27, ReplicaUnhealthy=19, etc. |
| Match? | **Exact match.** Both query `ContainerAppSystemLogs_CL` in Log Analytics. |
| Time | 4.7s | ~3s |

#### Step 6: Database Metrics (24h)

| | CLI | MCP |
|---|---|---|
| Data | CPU=7.4%, Memory=54.2%, Storage=13.2%, Connections=10.1 | CPU=[7.39-8.09%], Memory=[52.6-57.8%], Storage=13.21%, Connections=[10.0-11.8] |
| Match? | **Yes.** MCP returns all 24 hourly buckets; CLI returned latest hour avg. Consistent values. |
| Time | 0.8s | ~3s |

#### Step 7: Dependency Health (24h)

| | CLI | MCP |
|---|---|---|
| Data | postgresql → 742 calls, 0 failures | postgresql → 9,650 calls, 0 failures |
| Match? | **Same pattern, different counts.** App Insights vs Log Analytics. Zero failures both ways. |
| Time | 1.2s | ~3s |

#### Step 8: Console Logs

| | CLI | MCP |
|---|---|---|
| Data | 15 lines of structured JSON: `dashboard.built`, `step.completed`, `user.upserted`, `auth.login.success` — all `info` level, healthy | **Cannot get this.** No MCP tool for Container Apps console logs. |
| Time | 4.3s | N/A |

#### Step 9: Fired Alerts (24h)

| | CLI | MCP |
|---|---|---|
| Data | Empty (no fired alerts) | Empty (no activity logs) |
| Match? | **Yes.** |
| Time | 1.4s | ~3s |

### Aggregate Metrics

| Metric | CLI | MCP |
|---|---|---|
| Steps completed | **9/9** | 7/9 (missing Container App status + console logs) |
| Total wall-clock | **~18s** (9 commands) | ~21s (7 calls + 2 impossible) |
| Data accuracy | Queries App Insights directly — exact 24h window | Queries Log Analytics — wider window (more data, different counts) |
| Exceptions found | 0 | **221** (MCP found more via `AppExceptions`) |
| Context consumed (estimated) | ~8K tokens (skill instructions + terminal output) | ~20K tokens (skill + tool schemas loaded at session start + response JSON) |
| Coverage gaps | None | No Container App `show`, no console logs |

### Key Findings

1. **MCP caught more exceptions** — `AppExceptions` in Log Analytics had 221 exceptions that the App Insights `exceptions` query returned zero for. **Root cause identified**: `az monitor app-insights query` has a default server-side time range of ~1 hour. The KQL `where timestamp > ago(7d)` only filters *within* that window — it doesn't expand it. You must pass `--offset P7D` to access 7 days. With `--offset P7D`, App Insights returns identical data to Log Analytics (OAuthError=86 vs 87, off by 1 from ingestion timing). **Log Analytics is the source of truth** — it has no default time clipping and stores ~37 days of data. The skill has been updated to include `--offset` on all `az monitor app-insights query` calls.

2. **MCP cannot replace CLI for Container Apps** — No way to get provisioning state, replicas, or console logs. These are the #1 "is the app alive?" checks.

3. **Data counts differed ~20x** — This was NOT a Log Analytics vs App Insights discrepancy. It was a **missing `--offset` flag bug** in the CLI skill. CLI was querying a ~1 hour window while MCP (via Log Analytics) queried the full 24h. Fixed.

4. **Speed is comparable** — CLI ~2s/cmd avg, MCP ~3s/call. The extra hop adds ~1s but isn't dramatic.

5. **Context cost is the real MCP tax** — CLI output IS context (terminal output flows to the LLM), but CLI doesn't pay the upfront cost of loading tool definitions. Azure MCP loads ~15,000 tokens of tool schemas (monitor, resourcehealth, postgres namespaces) before any query runs. Both approaches consume ~5,000 tokens of per-query output. The difference is the ~15,000 token upfront schema tax that MCP pays and CLI doesn't.

### Actual Token Usage (from Copilot session logs)

Parsed from `~/Library/Application Support/Code/User/workspaceStorage/.../chatSessions/*.jsonl` using `scripts/parse_copilot_tokens.py`:

```
Session: f56eb1e1-e58e-45e7-9376-6a268980b5dd.jsonl (this research session)

Turn    Prompt     Output      Total | Breakdown
T1      79,566        258     79,824 | System=6%, Tool Defs=23%, Messages=19%, Files=8%, Tool Results=44%
T2     154,754        207    154,961 | System=4%, Tool Defs=14%, Messages=15%, Files=5%, Tool Results=62%
T3     188,693         96    188,789 | System=3%, Tool Defs=12%, Messages=20%, Files=4%, Tool Results=61%
T4     193,261         70    193,331 | System=3%, Tool Defs=12%, Messages=22%, Files=4%, Tool Results=60%
T5     196,565         64    196,629 | System=3%, Tool Defs=12%, Messages=23%, Files=4%, Tool Results=59%
T6     221,594        283    221,877 | System=3%, Tool Defs=10%, Messages=30%, Files=3%, Tool Results=54%
SUM  1,034,433        978  1,035,411
Peak: 221,594 tokens (23.7% of 935,805 context window)
```

**What the real data shows:**
- **Tool Definitions ≈ 22K tokens** (23% of T1's 79K prompt = ~18,300 tokens; stays ~22K absolute as context grows)
- **Tool Results are the dominant cost** at 54-62% of each prompt — this is CLI output + MCP responses accumulating across turns
- **System Instructions ≈ 5K tokens** (3-6%)
- The tool definition cost is real (~22K) but **dwarfed by accumulated tool results** once you're past Turn 1
- To isolate CLI-only vs MCP-only costs, run each in a **fresh chat session** and compare T1 numbers

---

## External References

- [Azure MCP Server README](https://github.com/microsoft/mcp/blob/main/servers/Azure.Mcp.Server/README.md) — Official README with full service list and server modes
- [Azure MCP CLI Command Reference](https://github.com/microsoft/mcp/blob/main/servers/Azure.Mcp.Server/docs/azmcp-commands.md) — Complete command documentation (2,898 lines, 144 KB)
- [Azure MCP Server tools list](https://learn.microsoft.com/en-us/azure/developer/azure-mcp-server/tools/) — Official tool inventory on Microsoft Learn
- [Azure MCP Server GA announcement](https://devblogs.microsoft.com/visualstudio/azure-mcp-server-now-built-in-with-visual-studio-2026-a-new-era-for-agentic-workflows/) — VS 2026 integration
- [MCP registry entry for Azure](https://github.com/mcp/com.microsoft/azure) — Namespace list
- [10 Microsoft MCP Servers blog](https://developer.microsoft.com/blog/10-microsoft-mcp-servers-to-accelerate-your-development-workflow) — Overview of Azure MCP capabilities
- [Context window bloat discussion (HN)](https://news.ycombinator.com/item?id=46334424) — Real-world report of Azure DevOps MCP consuming 25% of context
- [Token efficiency with Azure MCP namespaces](https://dev.to/aws-builders/why-an-aws-architect-built-azure-powers-for-kiro-and-what-i-learned-2dg4) — Namespace filtering to reduce token usage
- [VS Code full MCP spec support](https://code.visualstudio.com/blogs/2025/06/12/full-mcp-spec-support) — MCP primitives (prompts, resources, tools)
- [Container Apps metrics reference](https://learn.microsoft.com/en-us/azure/container-apps/metrics) — Metric namespace `Microsoft.App/containerapps`
