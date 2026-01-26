# Azure Log Analytics KQL Queries

Useful queries for debugging and monitoring. Run in Azure Portal → Log Analytics.

## Errors

```kusto
// All errors (4xx and 5xx) in last 24h
traces
| where timestamp > ago(24h)
| where message == "request.completed"
| extend status_code = toint(customDimensions.http_status_code)
| where status_code >= 400
| extend
    http_method = tostring(customDimensions.http_method),
    http_route = tostring(customDimensions.http_route),
    user_id = tostring(customDimensions.user_id)
| project timestamp, http_method, http_route, status_code, user_id
| order by timestamp desc
```

```kusto
// Unhandled exceptions
traces
| where timestamp > ago(24h)
| where message == "request.completed"
| where tostring(customDimensions.outcome) == "exception"
| extend
    http_route = tostring(customDimensions.http_route),
    exception_type = tostring(customDimensions.exception_type),
    user_id = tostring(customDimensions.user_id)
| project timestamp, http_route, exception_type, user_id
| order by timestamp desc
```

## Performance

```kusto
// Slow requests (> 1 second)
traces
| where timestamp > ago(24h)
| where message == "request.completed"
| extend duration_ms = todouble(customDimensions.duration_ms)
| where duration_ms > 1000
| extend
    http_method = tostring(customDimensions.http_method),
    http_route = tostring(customDimensions.http_route)
| project timestamp, http_method, http_route, duration_ms
| order by duration_ms desc
```

```kusto
// P50, P90, P99 latency by endpoint
traces
| where timestamp > ago(24h)
| where message == "request.completed"
| extend
    http_route = tostring(customDimensions.http_route),
    duration_ms = todouble(customDimensions.duration_ms)
| summarize
    p50 = percentile(duration_ms, 50),
    p90 = percentile(duration_ms, 90),
    p99 = percentile(duration_ms, 99),
    count = count()
    by http_route
| where count > 10
| order by p99 desc
```

## User Investigation

```kusto
// Single user's request history
let target_user = "user_abc123";  // Replace with actual user_id
traces
| where timestamp > ago(7d)
| where message == "request.completed"
| where tostring(customDimensions.user_id) == target_user
| extend
    http_method = tostring(customDimensions.http_method),
    http_route = tostring(customDimensions.http_route),
    status_code = toint(customDimensions.http_status_code),
    duration_ms = todouble(customDimensions.duration_ms)
| project timestamp, http_method, http_route, status_code, duration_ms
| order by timestamp desc
```

```kusto
// Users experiencing errors
traces
| where timestamp > ago(24h)
| where message == "request.completed"
| extend
    user_id = tostring(customDimensions.user_id),
    status_code = toint(customDimensions.http_status_code)
| where isnotempty(user_id) and status_code >= 400
| summarize error_count = count() by user_id
| order by error_count desc
```

## Traffic

```kusto
// Requests per minute (last hour)
traces
| where timestamp > ago(1h)
| where message == "request.completed"
| summarize requests = count() by bin(timestamp, 1m)
| render timechart
```

```kusto
// Traffic by endpoint
traces
| where timestamp > ago(24h)
| where message == "request.completed"
| extend http_route = tostring(customDimensions.http_route)
| summarize request_count = count() by http_route
| order by request_count desc
```
