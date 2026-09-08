# Alert response guides

These guides cover the first response to production alerts. Run queries in the
Application Insights **Logs** blade unless a section says to use the Log
Analytics workspace. Replace `dev` if the alert came from another environment.

Start with the action or error, follow its operation/attempt ID through related
telemetry, then use `verification.attempt.id` to look up the saved submission
and feedback in the database when authorized. Do not duplicate those payloads
in logs or public incident notes. Native URL paths and unexpected exception
details are available; query credentials are removed from URL fields. See
[Telemetry](../contributing.html#telemetry) for the collection boundaries.

## Signal contracts

| Alert resource | Canonical source | Audit result |
| --- | --- | --- |
| `availability` | Application Insights standard web-test metric | Unchanged; platform-owned uptime signal. |
| `api_unhandled_exception` | `unhandled.exception` structured exception log | Unchanged; the FastAPI exception boundary emits it once. |
| `api_telemetry_pipeline_failure` | `telemetry.configure.failed` JSON stdout log | Narrowed to the app-owned setup signal; removed the Azure SDK's internal logger text. |
| `verification_attempt_system_error` | `verification.attempt.completed` structured business log | Emitted only after PostgreSQL accepts the final outcome. |
| `verification_llm_immediate_failure` | `verification.llm_grading.failed` structured business log | Unchanged; bounded `error.type` remains the alert dimension. |
| `verification_llm_transient_failure` | `verification.llm_grading.failed` structured business log | Unchanged; bounded `error.type` remains the alert dimension. |
| `verification_attempt_stuck` | `verification.attempt.stuck` business log or `verification.worker.failed` error log | Queued/executing overdue work and fatal worker failures, under the API role. |
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

Use only a compatible rollback when failures began directly after a deployment.
For the session cutover, prefer a forward fix or a session-aware known-good
revision: old identity-cookie code would undo revocation. Do not suppress the
exception or disable the alert. If a
dependency is transiently unavailable, restore that dependency and confirm the
exact exception alert returns to a healthy state.

## Repository ownership verification

For repository checks, inspect the `github_repository_ownership` verification
step. A `failed` result means wrong ownership or a missing/private repository,
not a GitHub outage. A learner who changed their username can sign out, sign in
again, and submit a new attempt; reauthentication does not fix a repository
owned by someone else.

An `unavailable` result leaves the attempt incomplete. Correlate
`github.ownership.api_error` or `github.ownership.invalid_metadata` with bounded
HTTP status/error categories and dependency failures. Do not bypass ownership
to work around an outage or copy identity values, repository links, tokens, or
provider response bodies into incident notes.

## GitHub upstream verification failures

An incomplete attempt means verification could not finish, not that the
learner's work failed. Any attempted evidence fetch that fails with a network
or non-404 GitHub error stops grading. Genuine missing/private resources retain
their existing 404 feedback and do not increment `github.api_error`.

Inspect the bounded `error.type` and, for responses, `http.response.status_code`:

| Category | Investigation |
| --- | --- |
| `rate_limit` | Check GitHub quota and throttling; wait for recovery before retrying. |
| `provider_unavailable` | Check GitHub service availability and dependency failures. |
| `authentication` | Check the application's GitHub credential/configuration, not learner code. |
| `authorization` | Check integration permissions and repository access; distinguish rate-limited 403s. |
| `client_error` | Check the HTTP status and integration request contract. |
| `network` | Check connectivity, DNS, and timeouts; there is no HTTP response status. |

Exhausted 429/5xx responses now appear under `rate_limit`/`provider_unavailable`
rather than `network`. Profile, HEAD, and raw-file failures now reach the shared
mapper; increases in incomplete attempts or category counts can reflect corrected
handling rather than a new outage. Count once per final mapping, not per retry.
Raw-file reads still make one request per file.

Retry after transient recovery and investigate persistent service trouble.
Do not ask learners to change their work to fix application credentials, bypass
ownership checks, or sign in again as a general outage fix. Historical attempts
without a specific saved cause do not establish which dependency failed.

## Incomplete grading evidence

Inspect `verification.error.code` on `verification.attempt.completed`, the
associated `verification.step`, and `verification.evidence.assembled`.
An incomplete result has no learner rubric score and does not count as a failed
learner attempt. Prior completions remain intact.

| Code | Investigation and recovery |
| --- | --- |
| `evidence.required_missing` | Completed learner feedback, not a service outage. Check the published required paths; other files cannot substitute for required workflow source. |
| `evidence.changed` | A selected known-present file disappeared. Retry after the repository stops changing; do not label this initial absence. |
| `evidence.file_limit` | Compare selected file count with the task's bound. All selected optional evidence counts too. |
| `evidence.item_limit` | A complete item exceeds its UTF-8 byte bound. Do not truncate the item. |
| `evidence.total_limit` | Complete selected content exceeds the bundle bound. Do not drop optional files or split the rubric into partial grades. |
| `evidence.selection` | Investigate contract mismatch, invalid packets, or incomplete discovery; no partial packet may be graded. |
| `evidence.configuration` | Investigate the registered task policy, configured evidence requirements, and repository target. |

Budget, selection, and configuration failures require service attention.
Retrying unchanged work may not help. Do not ask learners to shrink valid
submissions or delete valid optional bonus evidence. Use bounded counts/bytes
to investigate the configured contract and prompt resource needs before changing
limits; do not raise caps merely to pass a fixture. GitHub retrieval failures
keep their upstream categories, and a truncated tree must never establish a
missing-file decision. Provider context rejection remains an incomplete service
result, not permission to grade partial evidence.

The evidence event contains only `evidence.outcome`, `evidence.reason`,
`evidence.selected_count`, `evidence.collected_count`, and `evidence.total_bytes`.
Outcomes are `complete`, `required_missing`, `retrieval_failed`, or `incomplete`;
reasons are `complete`, `retrieval`, or the seven `evidence.*` codes above.
Correlate with the existing bounded task/check IDs on `verification.step`, not
new evidence dimensions. Do not copy source, submitted text, hashes, repository
URLs, arbitrary paths, or learner identities into telemetry or incident notes.
Old attempts without a saved bounded cause do not prove which limit was hit.
Recovery does not authorize historical regrading, production data changes, new
alert thresholds, or automatic learner retries.

## Session lifecycle and rejected OAuth identity

`auth.session.rejected` records bounded `auth.session.reason` values. Expiry,
unknown sessions, and legacy-cookie cutover are expected info events, not
automatic compromise alerts. Malformed credentials and account-invariant
problems are warnings. `auth.callback.identity_rejected` remains a handled
provider warning with `auth.identity.reason`. Inspect the reason and request
outcome; never request or copy cookies, digests, CSRF tokens, user identity,
OAuth state, or provider bodies.

Public pages stay available, protected API/HTMX routes return 401, and browser
page navigation redirects to login. Rejected credentials are cleared; unrelated
OAuth state survives. Provider rejection redirects home without replacing a
valid existing login. Ordinary anonymous access emits no rejection event.

Expect a one-time rise in login traffic at the hard cutover: all old identity
cookies require a fresh GitHub login. Compare subsequent changes with the
revision, auth request statuses, and `auth.login.success`. Do not restore
legacy-cookie trust, numeric-ID coercion, or a cache-based bypass.

Every authenticated request now uses PostgreSQL. For unexpected 5xxs or slow
login/navigation, correlate database dependency latency, connection/pool errors,
lock waits, migration completion, and API runtime table grants. Check
`auth_sessions` schema readiness and the configured API role's DML privileges,
not just database connectivity. A store outage must remain a real failure:
neither successful logout nor anonymous fallback is safe.

Cookie cleanup alone is not revocation. `auth.session.revoked` means the
transaction committed, with scope `current` or `all` and aggregate count only.
Current logout invalidates copies of that session; other browsers stay signed
in. Sign out everywhere invalidates all current app sessions. It does not
revoke GitHub sessions or authorization, prevent genuinely later logins, or
cancel already-authorized requests and running verification work.

After cookie theft, use a trusted browser to sign in and choose Sign out
everywhere on Account. Secure a compromised GitHub account at GitHub as well.
Deleting an app account cascades all sessions; recreating it never revives
old cookies. Use real replay and independent-browser behavior to diagnose a
revocation defect, without copying credentials into telemetry or reports.

Successful logins opportunistically prune at most 100 expired rows.
`auth.session.pruned` reports committed aggregate counts. To investigate
retention backlog, use aggregate idle/absolute-expired counts only, never
session records or identifiers. No scheduler or fixed removal deadline exists;
expired rows cannot authenticate while awaiting cleanup. Sustained backlog
requires a separately scoped retention decision, not an assumed timer.

A persisted OAuth identity that differs from the validated provider identity is
an application invariant failure. It should not commit or issue a new session;
investigate it through the existing unhandled-exception guide above.
See [Authentication and sessions](../contributing.html#authentication-and-sessions).

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
| where cloud_RoleName == "learn-to-cloud-api"
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
2. Correlate the attempt's creation, execution span, and completion in API telemetry.
3. Check API worker health, dependencies, and the persisted attempt row.

### Detailed Kusto

```kusto
traces
| where timestamp > ago(2h)
| where cloud_RoleName == "learn-to-cloud-api"
| where message == "verification.attempt.completed"
| extend
    Outcome = tostring(customDimensions["verification.outcome"]),
    AttemptId = tostring(customDimensions["verification.attempt.id"])
| where Outcome in ("server_error", "cancelled")
| project timestamp, AttemptId, Outcome, cloud_RoleName, customDimensions
| order by timestamp desc
```

### Likely causes

- A verification dependency or execution failed.
- Execution timed out, or shutdown interrupted it.
- Overdue cleanup finalized work abandoned by a process crash.

### Escalation

Escalate when multiple learners are affected, the same stage repeatedly fails,
or retries produce another system outcome. Include attempt IDs, outcomes,
failure stage, dependency errors, and API revision.

### Safe recovery

Fix the underlying dependency or code path before asking the learner to retry.
Do not rewrite a final outcome or replay an execution. Once the cause is fixed,
the learner can submit a new attempt.

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
2. Confirm the API revision and model deployment configuration.
3. For transient categories, check Foundry and Azure service health, quotas,
   outbound connectivity, and whether the count continues after the alert
   window.

### Detailed Kusto

```kusto
traces
| where timestamp > ago(2h)
| where cloud_RoleName == "learn-to-cloud-api"
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
The worker separately bounds the entire attempt to 180 seconds by default;
that deadline can cancel grading before the SDK timeout and produces a saved
attempt failure rather than an exhausted SDK error.

## Verification active beyond limit

### Meaning

An attempt waited too long for a claim, an execution exceeded its limit, or the
API's sequential verification loop failed. One alert covers these related
availability failures without a separate worker-death alert. The bounded
`StuckReason` dimension is `queued_beyond_limit`, `execution_beyond_limit`, or
`worker_failed`. The first two come from `verification.attempt.stuck`; the last
comes from `verification.worker.failed`. The alert accepts trace or exception
telemetry, but the worker logs only `error.type` to avoid leaking provider
responses or evidence.

The worker and HTTP server share `learn-to-cloud-api`. Both `/health` and
`/ready` return 503 when the worker task has finished, allowing restart and
availability detection. Healthy probes indicate a live task, not that queued
work is progressing within its limit; the overdue signal covers that separately.
`verification.worker.failed` is not the HTTP-only `unhandled.exception`.

### First checks

1. Use the alert dimension to identify the bounded stuck reason.
2. Capture attempt ID and age for overdue work, or replica and error type for a
   worker failure (which need not have an attempt ID).
3. Check the API revision, replica health, database connectivity, and dependency
   spans. Confirm queued/executing backlog in PostgreSQL; missing log events are
   not authoritative queue state.

### Detailed Kusto

```kusto
union traces, exceptions
| where timestamp > ago(4h)
| where cloud_RoleName == "learn-to-cloud-api"
| extend Event = coalesce(message, outerMessage)
| where Event in ("verification.attempt.stuck", "verification.worker.failed")
| extend
    AttemptId = tostring(customDimensions["verification.attempt.id"]),
    AttemptAgeSeconds = toint(customDimensions["verification.attempt.age_seconds"]),
    StuckReason = iff(Event == "verification.worker.failed", "worker_failed", tostring(customDimensions["verification.stuck.reason"]))
| where StuckReason in (
    "queued_beyond_limit",
    "execution_beyond_limit",
    "worker_failed"
)
| project
    timestamp,
    AttemptId,
    AttemptAgeSeconds,
    StuckReason,
    cloud_RoleInstance
| order by timestamp desc
```

### Likely causes

- Sequential processing cannot keep up, or no healthy process is claiming work.
- A dependency stalled or an API process exited during execution.
- The loop failed while claiming work or cleaning up overdue attempts.

### Escalation

Escalate when age keeps increasing, multiple attempts share the same reason, or
worker failures affect multiple replicas. Include attempt IDs when available,
bounded reason, age, revision, and database/dependency errors.

### Safe recovery

Restore database/dependency connectivity or fix the failing code, then restart
the affected API process through the normal deployment path if its worker died.
Confirm new execution-started events and saved completions. The worker's overdue
cleanup saves terminal outcomes for abandoned attempts; it does not retry or
resume them. Let learners submit again after recovery. Do not manually unclaim
work that may still be executing.

For the migration cutover, stop the old verification host **before** migration
`0062_api_verification_worker`. It marks every active attempt `server_error` with
cause `verification_interrupted`. Then start the new API worker, which only
claims attempts without a `started_at` value. There is no replay or checkpoint
migration.
