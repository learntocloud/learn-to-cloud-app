# Alert response guides

These guides cover the first response to production alerts. Run queries in the
Application Insights **Logs** blade unless a section says to use the Log
Analytics workspace. Replace `dev` if the alert came from another environment.

## Signal contracts

| Alert resource | Canonical source | Audit result |
| --- | --- | --- |
| `availability` | Application Insights standard web-test metric | Unchanged; platform-owned uptime signal. |
| `api_unhandled_exception` | `unhandled.exception` structured exception log | Unchanged; the FastAPI exception boundary emits it once. |
| `api_telemetry_pipeline_failure` | `telemetry.configure.failed` JSON stdout log | Narrowed to the app-owned setup signal; removed the Azure SDK's internal logger text. |
| `verification_attempt_system_error` | `verification.attempt.completed` structured business log | Unchanged; #780 owns this persisted final-outcome contract. |
| `verification_llm_immediate_failure` | `verification.llm_grading.failed` structured business log | Unchanged; bounded `error.type` remains the alert dimension. |
| `verification_llm_transient_failure` | `verification.llm_grading.failed` structured business log | Unchanged; bounded `error.type` remains the alert dimension. |
| `verification_attempt_stuck` | `verification.attempt.stuck` structured business log | Unchanged; #780 owns the reconciler contract. |
| `schema_drift` | `health.ready.schema_drift*` structured health logs | Unchanged; the query uses event names, not exception text or spans. |

## Unhandled API exception

### Meaning

The API emitted `unhandled.exception`, which is the final FastAPI exception
boundary. The exact event is stored in `AppExceptions.OuterMessage`.

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

## Rejected session or OAuth identity

`auth.session.identity_rejected` and `auth.callback.identity_rejected` are
handled warnings, not unhandled-exception alerts. Inspect their bounded
`auth.identity.reason` and the associated request outcome; do not request or
copy the cookie, user identity, OAuth state, or provider response body.

Session rejection removes only the application identity. Public pages remain
available, protected API/HTMX routes return 401, and browser page navigation
redirects to login. OAuth rejection redirects home without replacing an existing
valid login. Ordinary anonymous requests do not emit these warnings.

Compare an increase with the deployed revision and recent authentication
changes. An old malformed signed cookie, a faulty session-producing tool, or
unexpected provider data can explain a rejection; the warning alone does not
prove cookie forgery or account compromise. Reauthentication can replace a
malformed identity. Do not disable validation or restore numeric-ID coercion.

A persisted OAuth identity that differs from the validated provider identity is
an application invariant failure. It should not commit or issue a new session;
investigate it through the existing unhandled-exception guide above. Malformed
cookie decoding occurs earlier in middleware and is tracked separately in #834.
See the [telemetry schema](../observability/telemetry-schema.html) for reason values.

## Ignored optional profile names and staged schema rollout

`auth.callback.display_name_ignored` is a value-free warning, not rejected
identity or failed login. An unusable optional name becomes `NULL`; successful
login still emits `auth.login.success`. Missing or blank names produce no warning.
Do not request profile payloads or add names to logs, span attributes, metric
labels, or browser identity context. Unexpected database error diagnostics may
contain public profile values; no custom profile-error redaction is applied.
Keep those diagnostics within the restricted telemetry system, not alert
notifications. Tokens, credentials, and cookies remain prohibited.

During the [display-name rollout](../migrations.html#display-name-rollout-836),
compare existing login-success, callback-error, request-status, migration-job,
and schema-drift signals with the deployed revision. Wait for each full deployment
before merging the next layer. Confirm the cutover revision serves authenticated
profile/dashboard requests and old replicas are retired before column removal;
readiness alone cannot prove that. No new alert or user dimension is needed.

After legacy columns are removed, pre-cutover images are incompatible. Prefer
a forward fix; even a compatible cutover runtime needs schema-aware migration
tooling and expected revision-drift handling. Never rerun an older deployment
workflow as an assumed rollback. Schema downgrade does not restore discarded
legacy names, and dropping display-name storage loses refreshed names.

## Telemetry pipeline failure

### Meaning

The API emitted `telemetry.configure.failed` to JSON stdout because it could not
configure its Azure Monitor or local OTLP destination. The API continues serving
when this alert fires, but application telemetry is degraded. This signal does
**not** prove an Azure Monitor service fault or detect later transmission loss.

### First checks

1. Open the Log Analytics workspace used by the Container Apps environment.
2. Identify whether the signal is a missing destination or a setup exception.
3. Check the API revision, replica, and telemetry destination configuration.

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
    Reason = tostring(ParsedLog.reason),
    ErrorType = tostring(ParsedLog["error.type"])
| where Event == "telemetry.configure.failed"
| project
    TimeGenerated,
    RevisionName_s,
    ContainerGroupName_s,
    Event,
    Reason,
    ErrorType,
    Log_s
| order by TimeGenerated desc
```

### Likely causes

- `telemetry_destination_missing` means neither an Application Insights
  connection string nor an OTLP endpoint was configured.
- An invalid telemetry configuration or an SDK setup exception prevented
  telemetry initialization.

### Escalation

Escalate when setup failures persist or the telemetry gap prevents incident
response. Include revision names, timestamps, the `reason` value, and bounded
error type without including connection strings.

### Safe recovery

Correct the telemetry destination configuration. Do not rotate or expose the
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

## Verification LLM grading failures

### Meaning

The grader produced a bounded operational category after its OpenAI-compatible
SDK retry budget was exhausted. Notifications contain only the category, count,
15-minute window when applicable, and the safe query link. They never contain
learner data, attempt IDs, provider request IDs, prompts, completions, response
bodies, or raw exception text.

`llm.configuration`, `llm.authentication`, `llm.authorization`,
`llm.response_validation`, and `llm.unknown` page immediately after controlled
production smoke validation. `llm.rate_limit`, `llm.provider_unavailable`,
`llm.network`, and `llm.timeout` page only after three exhausted failures of
the same category in 15 minutes. Content filtering is a completed learner
rewrite path, not an error or alert.

### First checks

1. Start with the alert category and count; do not add customer information to
   the query.
2. Confirm the Functions revision and model deployment configuration.
3. For transient categories, check Foundry and Azure service health, quotas,
   outbound connectivity, and whether the count continues after the alert
   window.

### Detailed Kusto

```kusto
traces
| where timestamp > ago(2h)
| where message == "verification.llm_grading.failed"
| extend ErrorType = tostring(customDimensions["error.type"])
| where ErrorType in (
    "llm.configuration", "llm.authentication", "llm.authorization",
    "llm.rate_limit", "llm.provider_unavailable", "llm.network",
    "llm.timeout", "llm.response_validation", "llm.unknown"
)
| summarize FailureCount = count() by ErrorType, bin(timestamp, 15m)
| order by timestamp desc
```

For authorized support investigation, resolve a learner to an internal attempt
ID through the production database, then use that opaque ID and a narrow time
window to inspect correlated Application Insights spans. Do not add usernames,
provider IDs, or raw exception data to the alert, query annotations, or incident
notes.

### Safe recovery

Correct configuration, credentials, or permissions before retrying a controlled
production smoke validation. For a response-validation category, inspect the
deployed structured response contract and model deployment, not learner
evidence. Keep the SDK's 10-minute timeout until 100 successful calls have been
observed over 30 days; do not introduce a shorter deadline from an alert alone.

## Verification active beyond limit

### Meaning

The reconciler confirmed an attempt is still active beyond its allowed duration,
or it could not reliably query/recheck Durable status. The detector reads the
`verification.attempt.stuck` event; the alert dimension is limited to:
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
    DurableStatus = tostring(customDimensions["verification.durable.status"]),
    AttemptAgeSeconds = toint(customDimensions["verification.attempt.age_seconds"]),
    StuckReason = tostring(customDimensions["verification.stuck.reason"])
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
