# Alert response guides

Run queries in Application Insights Logs unless directed to the Log Analytics
workspace. Narrow the time window to the incident. For authorized investigation,
use operation and attempt IDs to correlate telemetry with saved database records.
Do not copy credentials, submitted evidence, provider bodies, or profile values
into notifications or incident notes. See [Telemetry](../telemetry.html).

## Signal contracts

Alert thresholds and dimensions are defined in
[`infra/monitoring.tf`](https://github.com/learntocloud/learn-to-cloud-app/blob/main/infra/monitoring.tf).
Use that source for configuration changes rather than duplicating it here.

| Alert resource | Signal | First response |
|----------------|--------|----------------|
| `availability` | Standard web-test metric | Check public health, API revision, and replica state. |
| `api_unhandled_exception` | `unhandled.exception` | Correlate the exception with its request and latest deployment. |
| `api_telemetry_pipeline_failure` | `telemetry.configure.failed` | Inspect JSON console logs and destination configuration. |
| `verification_attempt_system_error` | `verification.attempt.completed` | Inspect the saved system outcome and worker/dependency failures. |
| `verification_llm_immediate_failure` | `verification.llm_grading.failed` | Check the bounded category for configuration or contract failures. |
| `verification_llm_transient_failure` | `verification.llm_grading.failed` | Check quota, connectivity, and provider availability. |
| `verification_attempt_stuck` | `verification.attempt.stuck` or `verification.worker.failed` | Inspect queue age, worker health, and database connectivity. |
| `schema_drift` | `health.ready.schema_drift*` | Compare migration results and deployed code/database revisions. |

To follow an operation:

```kusto
let OperationId = "<operation-id>";
union requests, dependencies, exceptions, traces
| where timestamp > ago(2h)
| where operation_Id == OperationId
| order by timestamp asc
```

Escalate persistent or widespread failures, authentication/data-integrity impact,
or loss of the telemetry needed to investigate. Include the affected revision,
first/last occurrence, bounded category, and safe correlation IDs.

## Unhandled API exception

This signal comes from the final HTTP exception boundary. Compare the first
occurrence with deployment time and inspect the correlated request/dependencies.

```kusto
exceptions
| where timestamp > ago(2h)
| where cloud_RoleName == "learn-to-cloud-api"
| where outerMessage == "unhandled.exception"
| project timestamp, operation_Id, cloud_RoleInstance, type, innermostMessage, details
| order by timestamp desc
```

Restore a failed dependency or fix the failing code. Use only a
[schema-compatible rollback](../migrations.html#recovery); do not suppress the
exception or restore legacy authentication to clear the alert.

## Telemetry pipeline failure

The API can continue serving after telemetry setup fails. This event identifies
missing configuration or setup exceptions, not later transmission loss or a
proven Azure Monitor outage.

Run this in the Container Apps environment's **Log Analytics workspace**:

```kusto
let Environment = "dev";
ContainerAppConsoleLogs_CL
| where TimeGenerated > ago(2h)
| where ContainerAppName_s == strcat("ca-ltc-api-", Environment)
| where ContainerName_s == "api"
| extend ParsedLog = parse_json(Log_s)
| where tostring(ParsedLog.event) == "telemetry.configure.failed"
| project TimeGenerated, RevisionName_s, ContainerGroupName_s,
    Reason = tostring(ParsedLog["telemetry.configuration.reason"]),
    ErrorType = tostring(ParsedLog["error.type"])
| order by TimeGenerated desc
```

Replace `dev` with the affected environment. `telemetry_destination_missing`
means neither destination was configured; a setup exception carries an error
type instead. Correct configuration and confirm new requests, dependencies, and
logs arrive. Never expose connection strings in the report.

## Schema drift

Distinguish revision mismatch from failure to query the revision. Check the
migration job result, deployed image, database connectivity, and runtime grants.

```kusto
traces
| where timestamp > ago(2h)
| where cloud_RoleName == "learn-to-cloud-api"
| where message in ("health.ready.schema_drift", "health.ready.schema_drift_check_failed")
| project timestamp, message, customDimensions
| order by timestamp desc
```

Use a verified forward migration or restore access, then confirm the signal
clears. Never edit the Alembic version table merely to clear an alert.
Readiness revision checks are not proof of full schema compatibility.

## Verification final failures

The completion event is emitted after the final outcome commits. System outcomes
do not mean the learner failed the assignment.

```kusto
traces
| where timestamp > ago(2h)
| where cloud_RoleName == "learn-to-cloud-api"
| where message == "verification.attempt.completed"
| extend Outcome = tostring(customDimensions["verification.outcome"]),
    AttemptId = tostring(customDimensions["verification.attempt.id"])
| where Outcome in ("server_error", "cancelled")
| project timestamp, AttemptId, Outcome, customDimensions
| order by timestamp desc
```

Correlate creation, execution, and completion with worker health and dependencies.
Fix the cause before asking the learner to submit again. Do not rewrite a final
outcome or replay an execution as an incident workaround.

## Verification LLM grading failures

Use the bounded category to separate configuration, authentication, authorization,
or response-contract failures from rate limits, network errors, timeouts, and
provider unavailability. Content filtering is a learner rewrite path, not an
operational error.

```kusto
traces
| where timestamp > ago(2h)
| where cloud_RoleName == "learn-to-cloud-api"
| where message == "verification.llm_grading.failed"
| extend ErrorType = tostring(customDimensions["error.type"])
| summarize FailureCount = count() by ErrorType, bin(timestamp, 15m)
| order by timestamp desc
```

Check the deployed model configuration, service health, quota, and outbound
connectivity as appropriate. Diagnose response-contract failures without copying
learner evidence or provider responses into telemetry.
After correction, perform only an authorized controlled smoke submission.

The worker deadline bounds the whole attempt and can cancel grading before the
SDK retry/timeout budget finishes. That produces an attempt failure rather than
necessarily an exhausted SDK error. Do not change timeout policy solely to quiet
an alert.

## Verification active beyond limit

The API and worker share the `learn-to-cloud-api` role. Both health endpoints
return 503 when the worker task has finished. Healthy probes show a live task,
not that queued work is progressing.

```kusto
union traces, exceptions
| where timestamp > ago(4h)
| where cloud_RoleName == "learn-to-cloud-api"
| extend Event = coalesce(message, outerMessage)
| where Event in ("verification.attempt.stuck", "verification.worker.failed")
| extend AttemptId = tostring(customDimensions["verification.attempt.id"]),
    AttemptAgeSeconds = toint(customDimensions["verification.attempt.age_seconds"]),
    StuckReason = iff(Event == "verification.worker.failed", "worker_failed", tostring(customDimensions["verification.stuck.reason"]))
| project timestamp, AttemptId, AttemptAgeSeconds, StuckReason, cloud_RoleInstance
| order by timestamp desc
```

For `queued_beyond_limit` or `execution_beyond_limit`, inspect persisted backlog,
capacity, and stalled dependencies. For `worker_failed`, identify the replica and
bounded error type; a worker failure need not have an attempt ID.
Missing log events are not authoritative queue state.

Restore dependencies or fix the loop failure, then restart an affected process
through the normal deployment path. Confirm fresh starts and saved completions.
Overdue cleanup terminalizes abandoned attempts; it does not resume them.
Never manually unclaim work that might still be executing.

## Repository ownership verification

Inspect the `github_repository_ownership` step. Wrong ownership or a
missing/private repository is learner feedback; GitHub access, network, and
invalid-metadata failures leave verification incomplete.
A learner who renamed their account can sign out, sign in, and submit again.
That does not fix a repository owned by someone else.

Never bypass ownership to work around an outage.

## GitHub upstream verification failures

Inspect bounded `error.type` and `http.response.status_code` when present.
Distinguish rate limits from access errors, including rate-limited 403s.
Network failures have no HTTP status. A genuine initial 404 retains its
missing/private-resource meaning, not an outage classification.

Restore application credentials, permissions, connectivity, or provider
availability before retrying. Do not tell learners to modify their work or
reauthenticate as a general GitHub-outage fix.

## Incomplete grading evidence

Inspect `verification.error.code` on the completion event, the associated
`verification.step`, and `verification.evidence.assembled`.
An incomplete result has no partial rubric score and does not count as failed
learner work.

| Cause | Recovery |
|-------|----------|
| Required work absent | Learner corrects the published missing requirement. |
| A selected file disappeared | Retry after the repository stops changing. |
| Retrieval failed | Resolve the upstream failure first. |
| Size/count limit, selection, or configuration failure | Investigate the task contract and service limits; unchanged retries may not help. |

Use the configured
[`task policies`](https://github.com/learntocloud/learn-to-cloud-app/tree/main/packages/learn-to-cloud-shared/src/learn_to_cloud_shared/verification/tasks)
and
[`evidence validation`](https://github.com/learntocloud/learn-to-cloud-app/blob/main/packages/learn-to-cloud-shared/src/learn_to_cloud_shared/verification/evidence.py)
to interpret the saved cause. A truncated tree cannot establish absence.
Do not drop optional evidence, truncate files, grade partial packets, or ask
learners to shrink valid submissions to fit a service bug.
Recovery does not authorize historical regrading or production data changes.

## Session lifecycle and rejected OAuth identity

Inspect bounded rejection reasons and request outcomes. Expired and unknown
sessions are expected, not automatic compromise alerts. Ordinary anonymous
access emits no rejection event. See
[Authentication and sessions](../authentication.html) for the response contract.

For unexpected login/navigation failures, check database latency, pool/lock
errors, migration results, and runtime-role grants. A session-store outage must
remain a service failure, never a successful logout or anonymous fallback.

Cookie clearing alone is not revocation. Diagnose using copied-cookie rejection
and independent-browser behavior without exposing credentials. A persisted
identity mismatch must not commit or issue a session; investigate it through
the unhandled-exception procedure.

After cookie theft, sign in on a trusted browser and use Sign out everywhere.
Secure a compromised GitHub account separately. App revocation neither revokes
GitHub authorization nor cancels already-authorized work.

## Ignored optional profile names

`auth.callback.display_name_ignored` is a value-free warning, not rejected
identity or failed login. Do not request profile payloads to investigate it.
Unexpected database diagnostics can contain public profile values; keep them
within restricted telemetry rather than notifications or incident notes.
