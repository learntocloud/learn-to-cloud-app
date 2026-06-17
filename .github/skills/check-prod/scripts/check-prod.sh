#!/usr/bin/env bash
# =============================================================================
# Production Health Check: data collector
# =============================================================================
# Gathers all 14 read-only production health signals in one pass and prints a
# single JSON object to stdout. This script ONLY collects data. The verdict
# logic and report formatting live in SKILL.md, where the agent applies
# judgment to the raw signals this script returns.
#
# Usage:
#   bash scripts/check-prod.sh                 # all checks, JSON to stdout
#   bash scripts/check-prod.sh --discover-only # just resource discovery
#
# Requirements: az CLI (logged in via `az login`), curl, jq.
# All queries are read-only. Resource group is rg-ltc-dev.
#
# Exit codes:
#   0  data collected (inspect the JSON for per-check results)
#   2  not authenticated to Azure (run `az login`)
#   3  a required tool (az/curl/jq) is missing
#   4  a required resource could not be discovered
# =============================================================================

set -uo pipefail

RG="rg-ltc-dev"
WINDOW_HOURS=24

# ---------------------------------------------------------------------------
# Preconditions
# ---------------------------------------------------------------------------
for tool in az curl jq; do
    if ! command -v "$tool" >/dev/null 2>&1; then
        echo "Error: required tool '$tool' is not installed." >&2
        exit 3
    fi
done

ACCOUNT_JSON="$(az account show -o json 2>/dev/null)" || {
    echo "Error: not authenticated to Azure. Run 'az login' first." >&2
    exit 2
}
SUBSCRIPTION="$(echo "$ACCOUNT_JSON" | jq -r '.id')"

START_TIME="$(date -u -d "${WINDOW_HOURS} hours ago" +%Y-%m-%dT%H:%M:%SZ)"
END_TIME="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

# ---------------------------------------------------------------------------
# Step 0: Resource discovery
# ---------------------------------------------------------------------------
discover() {
    local ca_name log_name psql_name appi_name
    ca_name="$(az resource list -g "$RG" --resource-type "Microsoft.App/containerApps" \
        --query "[?contains(name, 'api')].name | [0]" -o tsv 2>/dev/null)"
    [ -z "$ca_name" ] && ca_name="$(az resource list -g "$RG" \
        --resource-type "Microsoft.App/containerApps" --query "[0].name" -o tsv 2>/dev/null)"
    log_name="$(az resource list -g "$RG" \
        --resource-type "Microsoft.OperationalInsights/workspaces" \
        --query "[0].name" -o tsv 2>/dev/null)"
    psql_name="$(az resource list -g "$RG" \
        --resource-type "Microsoft.DBforPostgreSQL/flexibleServers" \
        --query "[0].name" -o tsv 2>/dev/null)"
    appi_name="$(az resource list -g "$RG" \
        --resource-type "microsoft.insights/components" \
        --query "[0].name" -o tsv 2>/dev/null)"

    if [ -z "$ca_name" ] || [ -z "$log_name" ] || [ -z "$psql_name" ]; then
        echo "Error: could not discover required resources in $RG." >&2
        echo "  containerApp=$ca_name workspace=$log_name postgres=$psql_name" >&2
        exit 4
    fi

    local ca_detail
    ca_detail="$(az containerapp show --name "$ca_name" --resource-group "$RG" \
        --query "{fqdn:properties.configuration.ingress.fqdn, provisioningState:properties.provisioningState, latestRevision:properties.latestRevisionName, minReplicas:properties.template.scale.minReplicas, maxReplicas:properties.template.scale.maxReplicas}" \
        -o json 2>/dev/null)"

    jq -n \
        --arg sub "$SUBSCRIPTION" --arg rg "$RG" \
        --arg ca "$ca_name" --arg log "$log_name" \
        --arg psql "$psql_name" --arg appi "$appi_name" \
        --argjson detail "${ca_detail:-null}" \
        '{subscription:$sub, resourceGroup:$rg, containerApp:$ca, workspace:$log,
          postgres:$psql, appInsights:$appi, containerAppDetail:$detail}'
}

DISCOVERY="$(discover)"
LOG_NAME="$(echo "$DISCOVERY" | jq -r '.workspace')"
PSQL_NAME="$(echo "$DISCOVERY" | jq -r '.postgres')"
CA_NAME="$(echo "$DISCOVERY" | jq -r '.containerApp')"
FQDN="$(echo "$DISCOVERY" | jq -r '.containerAppDetail.fqdn // empty')"
LATEST_REVISION="$(echo "$DISCOVERY" | jq -r '.containerAppDetail.latestRevision // empty')"

if [ "${1:-}" = "--discover-only" ]; then
    echo "$DISCOVERY" | jq '{discovery: .}'
    exit 0
fi

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# ---------------------------------------------------------------------------
# Helpers. Each writes raw JSON to "$TMP/<name>.json". On failure the file
# gets a fallback so the final assembly never breaks.
# ---------------------------------------------------------------------------
kql() { # name, query
    local name="$1" query="$2"
    { az monitor log-analytics query -w "$LOG_NAME" --analytics-query "$query" -o json 2>/dev/null \
        || echo '[]'; } > "$TMP/$name.json"
}

metrics() { # name, resource, resource_type, aggregation, metrics...
    local name="$1" resource="$2" rtype="$3" agg="$4"; shift 4
    { az monitor metrics list --resource "$resource" --resource-group "$RG" \
        --resource-type "$rtype" --metrics "$@" --interval PT1H --aggregation "$agg" \
        --start-time "$START_TIME" --end-time "$END_TIME" -o json 2>/dev/null \
        || echo '{}'; } > "$TMP/$name.json"
}

# Container/console logs live in either a *_CL custom table (with _s/_g column
# suffixes) or a standard table. Try the custom table first, fall back if empty.
kql_with_fallback() { # name, primary_query, fallback_query
    local name="$1" primary="$2" fallback="$3" result
    result="$(az monitor log-analytics query -w "$LOG_NAME" --analytics-query "$primary" -o json 2>/dev/null || echo '[]')"
    if [ "$(echo "$result" | jq 'length')" = "0" ]; then
        result="$(az monitor log-analytics query -w "$LOG_NAME" --analytics-query "$fallback" -o json 2>/dev/null || echo '[]')"
    fi
    echo "$result" > "$TMP/$name.json"
}

resource_health() {
    { az resource health availability-status list-by-resource-group --resource-group "$RG" \
        --subscription "$SUBSCRIPTION" -o json 2>/dev/null || echo '[]'; } > "$TMP/resource_health.json"
}

# ---------------------------------------------------------------------------
# Step 1: Live readiness probe (curl)
# ---------------------------------------------------------------------------
readiness() {
    if [ -z "$FQDN" ]; then
        echo '{"status":null,"response_time":null,"error":"no fqdn discovered"}' > "$TMP/readiness.json"
        return
    fi
    local out
    out="$(curl -s --max-time 5 -o /dev/null -w '%{http_code} %{time_total}' "https://$FQDN/ready" 2>/dev/null || echo '000 0')"
    jq -n --arg code "${out% *}" --arg t "${out#* }" \
        '{status:($code|tonumber), response_time:($t|tonumber)}' > "$TMP/readiness.json"
}

# ---------------------------------------------------------------------------
# Launch all checks in parallel
# ---------------------------------------------------------------------------
readiness &
resource_health &

kql availability_tests \
    "AppAvailabilityResults | where TimeGenerated > ago(24h) | summarize Total=count(), Failed=countif(Success == false), AvgDuration=avg(DurationMs)" &

kql request_health \
    "AppRequests | where TimeGenerated > ago(24h) | summarize P95=percentile(DurationMs, 95), Total=count(), Err4xx=countif(toint(ResultCode) >= 400 and toint(ResultCode) < 500), Err5xx=countif(toint(ResultCode) >= 500)" &

kql error_rate_trend \
    "AppRequests | where TimeGenerated > ago(7d) | summarize Total=count(), Failed=countif(Success == false) by bin(TimeGenerated, 1d) | extend ErrorRate=round(todouble(Failed)/todouble(Total)*100, 2) | order by TimeGenerated desc" &

kql exceptions \
    "AppExceptions | where TimeGenerated > ago(7d) | summarize Count=count() by ExceptionType, OuterMessage | order by Count desc | take 10" &

kql error_traces \
    "AppTraces | where TimeGenerated > ago(24h) and SeverityLevel >= 3 | summarize Count=count() by Message | order by Count desc | take 10" &

kql dependencies \
    "AppDependencies | where TimeGenerated > ago(24h) | summarize Count=count(), FailureCount=countif(Success == false), AvgDuration=round(avg(DurationMs), 1), P95Duration=round(percentile(DurationMs, 95), 1) by Type, Target | order by Count desc | take 15" &

metrics db_avg "$PSQL_NAME" "Microsoft.DBforPostgreSQL/flexibleServers" Average \
    cpu_percent memory_percent storage_percent active_connections &
metrics db_peak "$PSQL_NAME" "Microsoft.DBforPostgreSQL/flexibleServers" Maximum \
    cpu_percent memory_percent storage_percent active_connections &
metrics db_credits "$PSQL_NAME" "Microsoft.DBforPostgreSQL/flexibleServers" Minimum \
    cpu_credits_remaining cpu_credits_consumed &

metrics container_app "$CA_NAME" "Microsoft.App/containerApps" Maximum \
    UsageNanoCores WorkingSetBytes &

kql_with_fallback container_stability \
    "ContainerAppSystemLogs_CL | where TimeGenerated > ago(24h) and RevisionName_s == '${LATEST_REVISION}' | summarize Count=count() by Reason_s, Type_s | order by Count desc" \
    "ContainerAppSystemLogs | where TimeGenerated > ago(24h) and RevisionName == '${LATEST_REVISION}' | summarize Count=count() by Reason, Type | order by Count desc" &

kql fired_alerts \
    "AzureActivity | where TimeGenerated > ago(24h) | where OperationNameValue has 'microsoft.insights/metricalerts' or OperationNameValue has 'microsoft.insights/scheduledqueryrules' | where ActivityStatusValue == 'Activated' | extend AlertName=tostring(split(ResourceId, '/')[-1]) | project TimeGenerated, AlertName, ResourceId, Properties | order by TimeGenerated desc" &

kql business_metrics \
    "AppMetrics | where TimeGenerated > ago(24h) and Name in ('auth.login', 'submission.cooldown_active', 'user.deletion', 'step.completed', 'verification.attempt') | summarize Total=sum(Sum) by Name | order by Name asc" &

kql auth_ratio \
    "AppMetrics | where TimeGenerated > ago(24h) and Name == 'auth.login' | extend result = tostring(Properties['result']) | summarize Total=sum(Sum) by result" &

kql_with_fallback console_errors \
    "ContainerAppConsoleLogs_CL | where TimeGenerated > ago(24h) | where Log_s has 'Traceback' or Log_s has 'FATAL' or Log_s has 'OOMKilled' or Log_s has 'Segmentation fault' | summarize Count=count() by bin(TimeGenerated, 1h) | order by TimeGenerated desc" \
    "ContainerAppConsoleLogs | where TimeGenerated > ago(24h) | where Log has 'Traceback' or Log has 'FATAL' or Log has 'OOMKilled' or Log has 'Segmentation fault' | summarize Count=count() by bin(TimeGenerated, 1h) | order by TimeGenerated desc" &

wait

# ---------------------------------------------------------------------------
# Assemble final JSON
# ---------------------------------------------------------------------------
read_json() { cat "$TMP/$1.json" 2>/dev/null || echo 'null'; }

jq -n \
    --argjson discovery "$DISCOVERY" \
    --arg generated "$END_TIME" \
    --argjson readiness "$(read_json readiness)" \
    --argjson resource_health "$(read_json resource_health)" \
    --argjson availability_tests "$(read_json availability_tests)" \
    --argjson request_health "$(read_json request_health)" \
    --argjson error_rate_trend "$(read_json error_rate_trend)" \
    --argjson exceptions "$(read_json exceptions)" \
    --argjson error_traces "$(read_json error_traces)" \
    --argjson dependencies "$(read_json dependencies)" \
    --argjson db_avg "$(read_json db_avg)" \
    --argjson db_peak "$(read_json db_peak)" \
    --argjson db_credits "$(read_json db_credits)" \
    --argjson container_app "$(read_json container_app)" \
    --argjson container_stability "$(read_json container_stability)" \
    --argjson fired_alerts "$(read_json fired_alerts)" \
    --argjson business_metrics "$(read_json business_metrics)" \
    --argjson auth_ratio "$(read_json auth_ratio)" \
    --argjson console_errors "$(read_json console_errors)" \
    '{
        generated: $generated,
        discovery: $discovery,
        checks: {
            "1_readiness": $readiness,
            "2_resource_health": $resource_health,
            "3_availability_tests": $availability_tests,
            "4_request_health": $request_health,
            "5_error_rate_trend": $error_rate_trend,
            "6_exceptions": $exceptions,
            "6_error_traces": $error_traces,
            "7_dependencies": $dependencies,
            "8_db_avg": $db_avg,
            "8_db_peak": $db_peak,
            "8_db_credits": $db_credits,
            "9_container_app": $container_app,
            "10_container_stability": $container_stability,
            "11_fired_alerts": $fired_alerts,
            "12_business_metrics": $business_metrics,
            "12_auth_ratio": $auth_ratio,
            "13_console_errors": $console_errors
        }
    }'
