# Alert response guides

These guides cover the first response to production alerts. Run queries in the
Application Insights **Logs** blade unless a section says to use the Log
Analytics workspace. Replace `dev` if the alert came from another environment.

## Unhandled API exception

### Meaning

The API emitted `unhandled.exception`, which is the final FastAPI exception
boundary. The exact event is stored in `AppExceptions.OuterMessage`. This exact
detector replaces the retired broad API 5xx paging signal.

### First checks

1. Note the alert time, affected revision, exception type, request path, and HTTP
   method.
2. Check whether the same operation ID has a failed request or dependency.
3. Compare the first occurrence with the latest API deployment time.

### Detailed Kusto

```kusto
exceptions
| where timestamp > ago(2h)
| where cloud_RoleName == "learn-to-cloud-api"
| where outerMessage == "unhandled.exception"
| project
    timestamp,
    operation_Id,
    cloud_RoleInstance,
    type,
    outerMessage,
    innermostMessage,
    details
| order by timestamp desc
```

Correlate an occurrence with its request and dependencies:

```kusto
let OperationId = "<operation-id>";
union requests, dependencies, exceptions, traces
| where operation_Id == OperationId
| order by timestamp asc
```

### Likely causes

- An unexpected application exception escaped its route or service boundary.
- A new revision introduced an incompatible configuration or dependency.
- A downstream service returned a condition the API did not handle.

### Escalation

Escalate immediately if exceptions continue, affect authentication or data
integrity, or coincide with availability failures. Include the operation ID,
revision, path, exception type, and first/last timestamps.

### Safe recovery

Prefer rolling back the affected API revision when the failures began directly
after a deployment. Do not suppress the exception or disable the alert. If a
dependency is transiently unavailable, restore that dependency and confirm the
exact exception alert returns to a healthy state.

## Telemetry pipeline failure

### Meaning

The API could not configure Azure Monitor once, or the main Azure Monitor
exporter logged at least three non-retryable transmission records in 15 minutes.
This signal does **not** prove permanent telemetry loss or an Azure service
fault. QuickPulse (Live Metrics) diagnostics are intentionally excluded.

### First checks

1. Open the Log Analytics workspace used by the Container Apps environment.
2. Identify whether the signal is configuration failure or repeated main
   exporter transmission failure.
3. Check the API revision, replica, connection-string reference, outbound
   connectivity, and Azure Monitor service health.

### Detailed Kusto

```kusto
let Environment = "dev";
ContainerAppConsoleLogs_CL
| where TimeGenerated > ago(2h)
| where ContainerAppName_s == strcat("ca-ltc-api-", Environment)
| where ContainerName_s == "api"
| extend ParsedLog = parse_json(Log_s)
| extend
    Event = tostring(ParsedLog.event),
    Logger = tostring(ParsedLog.logger)
| extend
    IsConfigureFailure = Event == "telemetry.configure.failed",
    IsMainExporterFailure =
        Logger == "azure.monitor.opentelemetry.exporter.export._base"
        and Log_s contains "Envelopes could not be exported and are not retryable:"
| where IsConfigureFailure or IsMainExporterFailure
| project
    TimeGenerated,
    RevisionName_s,
    ContainerGroupName_s,
    Event,
    Logger,
    Log_s
| order by TimeGenerated desc
```

### Likely causes

- An invalid or unavailable Application Insights connection string prevented API
  startup telemetry configuration.
- Network, DNS, TLS, throttling, or authentication conditions blocked exporter
  transmission.
- A payload was rejected as non-retryable by the ingestion endpoint.

### Escalation

Escalate when configuration failures block a new API revision, exporter failures
continue for more than 30 minutes, or the telemetry gap prevents incident
response. Include revision names, timestamps, exporter logger, and the exact
error text without including connection strings.

### Safe recovery

Correct the secret reference, managed configuration, or outbound connectivity,
then restart or roll forward the affected revision. Do not rotate or expose the
connection string unless investigation confirms it is invalid. Confirm new
traces, requests, exceptions, logs, and metrics arrive after recovery.

## Schema drift

### Meaning

Three consecutive evaluations found either a mismatch between the database
Alembic head and the code head, or a failure while checking that relationship.

### First checks

1. Distinguish `health.ready.schema_drift` from
   `health.ready.schema_drift_check_failed`.
2. Check the deployed API revision and the latest migration job result.
3. Compare the database revision with the Alembic head in the deployed code.

### Detailed Kusto

```kusto
traces
| where timestamp > ago(2h)
| where cloud_RoleName in ("learn-to-cloud-api", "ca-ltc-api-dev")
    or cloud_RoleName has "learn-to-cloud-api"
    or cloud_RoleName has "ca-ltc-api"
| where message in (
    "health.ready.schema_drift",
    "health.ready.schema_drift_check_failed"
)
| project timestamp, message, severityLevel, customDimensions
| order by timestamp desc
```

### Likely causes

- The application image deployed before its migration completed.
- A migration failed or was only partially applied.
- The database was changed manually.
- The readiness check could not query the migration table.

### Escalation

Escalate immediately for migration failure, manual schema change, or any evidence
of data corruption. Include current/code revision values, migration job output,
API revision, and the exact readiness event.

### Safe recovery

Use the normal migration job to apply a verified forward migration. Never edit
the Alembic version table merely to clear the alert. If the check itself failed,
restore database connectivity or permissions, then wait for three clean
evaluations.

## Verification final failures

### Meaning

A verification attempt reached a final persisted outcome of `server_error` or
`cancelled`. The alert counts distinct attempt IDs and does not page for learner
validation failures.

### First checks

1. Capture the attempt ID and final outcome.
2. Correlate the attempt across API and verification Functions telemetry.
3. Check Durable Functions status, dependencies, and the persisted attempt row.

### Detailed Kusto

```kusto
traces
| where timestamp > ago(2h)
| where cloud_RoleName in (
    "learn-to-cloud-api",
    "ca-ltc-api-dev",
    "learn-to-cloud-verification-functions",
    "func-ltc-verification-dev"
)
    or cloud_RoleName has "learn-to-cloud-api"
    or cloud_RoleName has "verification-functions"
| where message == "verification.attempt.completed"
| extend
    Outcome = tostring(customDimensions["verification.outcome"]),
    AttemptId = tostring(customDimensions["verification.attempt.id"])
| where Outcome in ("server_error", "cancelled")
| project timestamp, AttemptId, Outcome, cloud_RoleName, customDimensions
| order by timestamp desc
```

### Likely causes

- A verification dependency or orchestration activity failed.
- The orchestration was cancelled during shutdown or recovery.
- Persisting or reading the final state failed.

### Escalation

Escalate when multiple learners are affected, the same stage repeatedly fails,
or retries produce another system outcome. Include attempt IDs, outcomes,
failure stage, dependency errors, and orchestration status.

### Safe recovery

Fix the underlying dependency or code path before asking the learner to retry.
Do not rewrite a final outcome. Use established replay/reset procedures only
after confirming they are safe for that attempt.

## Verification active beyond limit

### Meaning

The reconciler confirmed an attempt is still active beyond its allowed duration,
or it could not reliably query/recheck Durable status. The emitted event remains
`verification.attempt.stuck`; the alert dimension is limited to:
`active_beyond_limit`, `status_query_failed`, and `status_recheck_failed`.

### First checks

1. Use the alert dimension to identify the bounded stuck reason.
2. Capture attempt ID, Durable status, and attempt age from the matching record.
3. Check the verification Functions revision, host health, storage, and Durable
   task hub.

### Detailed Kusto

```kusto
traces
| where timestamp > ago(4h)
| where cloud_RoleName in (
    "learn-to-cloud-verification-functions",
    "func-ltc-verification-dev"
)
    or cloud_RoleName has "verification-functions"
    or cloud_RoleName has "func-ltc-verification"
| where message == "verification.attempt.stuck"
| extend
    AttemptId = tostring(customDimensions["verification.attempt.id"]),
    DurableStatus = tostring(customDimensions["durable_status"]),
    AttemptAgeSeconds = toint(customDimensions["attempt_age_seconds"]),
    StuckReason = tostring(customDimensions["stuck_reason"])
| where StuckReason in (
    "active_beyond_limit",
    "status_query_failed",
    "status_recheck_failed"
)
| project
    timestamp,
    AttemptId,
    DurableStatus,
    AttemptAgeSeconds,
    StuckReason,
    cloud_RoleInstance
| order by timestamp desc
```

### Likely causes

- An orchestration or activity is genuinely running beyond its limit.
- Durable storage or the management endpoint could not answer a status query.
- A race occurred while the reconciler rechecked a terminal transition.

### Escalation

Escalate when age keeps increasing, multiple attempts share the same reason, or
status queries fail across replicas. Include attempt IDs, bounded reason,
Durable status, age, revision, and storage/host errors.

### Safe recovery

Restore task-hub or host connectivity before changing attempt state. Terminate
or reset an orchestration only after confirming the attempt ID and persisted
state, and use the application's established recovery path rather than editing
Durable storage directly.
