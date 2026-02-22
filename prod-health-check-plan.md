# Plan: Prod Health Check Skill Improvements

## Approach

Add the 5 missing checks identified in the research to the existing skill. Each is a single query/command that slots into the existing step structure. No existing steps are modified — only additions.

**Why this approach**: The current skill is already lean (297 lines, 12 commands). The gaps are well-defined and each requires exactly 1 new command. There's no need to restructure — just fill in the holes.

---

## Changes

### File modified: `.github/skills/prod-health-check/SKILL.md`

#### 1. Add Step 1b: Live Readiness Probe (after Step 1)

Curl the app's own `/ready` endpoint directly. This catches cases where Azure says the container is "Running" but the app itself can't serve traffic (e.g., DB connection failed, init error).

```bash
## Step 1b: Live Readiness Probe

FQDN=$(az containerapp show -n $CA_NAME -g $RG --query properties.configuration.ingress.fqdn -o tsv)
curl -s -o /dev/null -w "ready_status=%{http_code} response_time=%{time_total}s\n" "https://$FQDN/ready"
```

**Look for**: `ready_status=200`. If 503, the app reports itself as not ready (check DB connectivity or init errors). Response time > 2s is a warning.

**Where to insert**: After Step 1, before Step 2.

#### 2. Add Step 1c: Availability Web Test Results (after Step 1b)

Surface results from the synthetic availability test already configured in Terraform (`azurerm_application_insights_standard_web_test`).

```bash
## Step 1c: Availability (Synthetic Uptime Test)

az monitor app-insights query --app $APPI_NAME -g $RG --offset P1D --analytics-query "
availabilityResults
| where timestamp > ago(24h)
| summarize Total=count(), Failed=countif(success == false), AvgDuration=avg(duration)
" --query "tables[0].rows[0]" -o tsv
```

**Look for**: `Failed` = 0. Availability tests run every 5 minutes from multiple regions — ~288 tests/day. Any failures indicate real downtime visible to users.

**Where to insert**: After Step 1b, before Step 2.

#### 3. Add Step 2b: Per-Endpoint Latency (after Step 2)

Break down the aggregate P95 by endpoint. A single slow endpoint (e.g., `/api/analytics`) can hide behind a healthy-looking aggregate.

```bash
## Step 2b: Per-Endpoint Latency (24h)

az monitor app-insights query --app $APPI_NAME -g $RG --offset P1D --analytics-query "
requests
| where timestamp > ago(24h)
| summarize P95=percentile(duration, 95), Count=count() by name
| where Count > 10
| order by P95 desc
| take 10
" --query "tables[0].rows" -o tsv
```

**Look for**: Any endpoint with P95 > 500ms deserves investigation. Exclude `/health` (always fast, skews aggregate).

**Where to insert**: After Step 2, before Step 3.

#### 4. Add Step 5b: Recent Deployments (after Step 5)

Show recent Container App revisions so you can correlate issues with deployments.

```bash
## Step 5b: Recent Deployments

az containerapp revision list -n $CA_NAME -g $RG \
  --query "reverse(sort_by([].{name:name, active:properties.active, created:properties.createdTime, state:properties.runningState}, &created)) | [:5]" \
  -o table
```

**Look for**: Revisions in `Failed` state, revisions created in the last few hours (recent deploys), inactive revisions with `Stopped` state (normal cleanup).

**Where to insert**: After Step 5, before Step 6.

#### 5. Add Step 3b: Error Rate Trend (after Step 3)

Show daily error rate over 7 days to identify gradual degradation that stays below alert thresholds.

```bash
## Step 3b: Error Rate Trend (7d)

az monitor app-insights query --app $APPI_NAME -g $RG --offset P7D --analytics-query "
requests
| where timestamp > ago(7d)
| summarize Total=count(), Failed=countif(success == false) by bin(timestamp, 1d)
| extend ErrorRate=round(todouble(Failed)/todouble(Total)*100, 2)
| order by timestamp desc
" --query "tables[0].rows" -o tsv
```

**Look for**: Rising `ErrorRate` trend even if each day is below the alert threshold. Stable or decreasing = healthy.

**Where to insert**: After Step 3, before Step 4.

#### 6. Update Summary Report Template

Add new rows to the summary table:

```
| Readiness Probe | ✅/🔴 | {status_code}, {response_time}s |
| Availability Test | ✅/⚠️ | {N} tests, {N} failed in 24h |
| Slowest Endpoints | ✅/⚠️ | {endpoint}: P95 {X}ms |
| Error Rate Trend | ✅/⚠️ | {stable/rising/falling} over 7d |
| Recent Deploys | ✅/⚠️ | {N} revisions in 24h, {N} failed |
```

---

## Final Step Order

| Step | Check | Commands | New? |
|------|-------|----------|------|
| 0 | Resource Discovery | 6 | Existing |
| 1 | Container App Status | 1 | Existing |
| **1b** | **Live Readiness Probe** | **1** | **New** |
| **1c** | **Availability Web Test** | **1** | **New** |
| 2 | Request Volume & Latency | 1 | Existing |
| **2b** | **Per-Endpoint Latency** | **1** | **New** |
| 3 | HTTP Errors | 1 | Existing |
| **3b** | **Error Rate Trend** | **1** | **New** |
| 4 | Exceptions | 1 | Existing |
| 5 | Container System Events | 3 | Existing |
| **5b** | **Recent Deployments** | **1** | **New** |
| 6 | Database Metrics | 2 | Existing |
| 7 | Dependency Health | 1 | Existing |
| 8 | Console Logs | 1 | Existing |
| 9 | Fired Alerts | 1 | Existing |

**Total: 12 existing commands + 5 new = 17 commands. Still lean.**

---

## Trade-offs

### Considered: Renumber all steps to sequential (1-14)

**Rejected.** Using `1b`, `1c`, `2b`, etc. preserves the existing step numbers so anyone familiar with the skill doesn't get confused. Renumbering would break mental models and any external references to "Step 5" etc.

### Considered: Add connection pool saturation check (SQLAlchemy pool metrics)

**Rejected for now.** The app doesn't expose pool metrics to telemetry. Would require code changes (`core/database.py`) to emit `pool_checkedout`, `pool_overflow` as custom metrics. That's a separate feature, not a skill change.

### Considered: Add `/health/dependencies` endpoint to the app

**Rejected for now.** Nice-to-have per the research, but the skill already checks dependencies via App Insights (Step 7). This is an app code change, not a skill change — different scope.

---

## Risks & Edge Cases

1. **`curl` to FQDN may fail from local network** — If running from a corporate network with outbound restrictions, curling the Azure FQDN could time out. The existing `az containerapp show` already confirms the FQDN, so this is a supplement, not a replacement. Add a 5-second timeout: `curl -s --max-time 5`.

2. **Availability results table may be empty** — If the Terraform web test was recently created or temporarily disabled, `availabilityResults` could return zero rows. The "Look for" guidance handles this.

3. **Revision list could be very long** — During heavy iterative development, there could be 50+ revisions. The query limits to the 5 most recent using `| [:5]`.

4. **Error rate trend with zero requests on a day** — If a day has zero requests (e.g., newly deployed), `todouble(Failed)/todouble(Total)` would divide by zero. KQL handles this gracefully (returns `NaN`), but note it in guidance.

5. **Step numbering document length** — Adding 5 steps with descriptions and code blocks adds ~80 lines to the skill file. From 297 → ~377 lines. Still well under the original 602 lines.

---

## Todo List

- [x] **Phase 1: Add new steps to SKILL.md**
  - [x] Insert Step 1b (Live Readiness Probe) after Step 1
  - [x] Insert Step 1c (Availability Web Test) after Step 1b
  - [x] Insert Step 2b (Per-Endpoint Latency) after Step 2
  - [x] Insert Step 3b (Error Rate Trend) after Step 3
  - [x] Insert Step 5b (Recent Deployments) after Step 5
- [x] **Phase 2: Update Summary Report template**
  - [x] Add new rows to the summary table
- [ ] **Phase 3: Validate**
  - [ ] Run "check prod" in a fresh chat session to verify all new steps execute correctly
  - [ ] Run `python3 scripts/parse_copilot_tokens.py` to measure token impact of the 5 new commands
