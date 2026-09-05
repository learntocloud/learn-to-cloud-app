# Telemetry schema

This document is the contract for telemetry emitted by Learn to Cloud code.
It covers the API, verification Functions, shared verification package, and
browser. Azure, OpenTelemetry, Durable Functions, and framework-owned fields
are documented separately because their schemas can change with SDK upgrades.

The contract follows three rules:

1. Emit the minimum data needed to operate the service.
2. Use OpenTelemetry semantic conventions when they fit; otherwise use a
   dotted, domain-prefixed application name.
3. Never emit usernames, database user IDs, submitted values, prompts,
   completions, tokens, query strings, raw exception messages, or arbitrary
   learner-controlled text.

## Destinations and ownership

| Producer | Destination | Application-owned signals |
| --- | --- | --- |
| FastAPI API | Workspace-backed backend Application Insights resource | Structured logs, selected exceptions, sanitized request/dependency attributes, and resource identity |
| Verification Functions | Same backend Application Insights resource through the Functions host | Structured verification lifecycle logs, verification spans, dependency spans, and resource identity |
| Browser | Separate workspace-backed frontend Application Insights resource | Page views and `htmx.transport_error` events |
| API JSON stdout | `ContainerAppConsoleLogs_CL` | Startup telemetry configuration failures when the exporter is unavailable |

The shared Log Analytics workspace has a 30-day retention setting in Terraform.
Access is restricted through Azure RBAC. Telemetry must not be copied into
alert notifications when an operator can investigate it in Application
Insights instead.

## Data classes

| Class | Meaning | Examples |
| --- | --- | --- |
| Operational | Bounded service state that does not describe a learner | Error category, HTTP status, revision, candidate count |
| Learner activity | Describes a verification or page action but does not identify the learner by itself | Requirement slug, verification result, bounded page family |
| Linkable | An opaque value that can be joined with restricted application data to identify one learner or submission | Verification attempt ID |
| Prohibited | Direct identity, secrets, or uncontrolled text that can contain sensitive data | User ID, username, query string, raw exception text, submitted URL |

Linkable telemetry requires an operational need, restricted access, and a
documented retention boundary. `verification.attempt.id` is the only approved
linkable application attribute.

## Resource attributes

These attributes identify the process that emitted a signal. They are attached
by `learn_to_cloud_shared.core.observability`.

| Canonical attribute | Producer | Purpose | Cardinality | Class | Decision |
| --- | --- | --- | --- | --- | --- |
| `service.name` | API and shared telemetry setup | Separate API and verification Function telemetry | Fixed service set | Operational | Keep |
| `service.version` | Container App API | Correlate a signal with a deployed revision | One value per revision | Operational | Keep |
| `service.instance.id` | API and Functions | Diagnose replica-specific failures | One value per running instance | Operational | Keep; do not include in notifications |

## HTTP attributes

Inbound API paths must be FastAPI route templates such as
`/steps/{step_uuid}`, never the concrete request path. Outbound HTTP dependency
URLs retain only the destination origin and replace the path with `/`.

Route discovery uses FastAPI's public route contexts so included and nested
router prefixes remain part of the template. Unmatched requests use `/unmatched`.
Expected authentication responses (401 or a 303 login redirect) remain request
telemetry, not unhandled exceptions or additional identity-bearing auth events.

The application currently writes both current and legacy OpenTelemetry HTTP
names because the Azure exporter and instrumentations can read different
generations of the convention. These are intentional compatibility aliases,
not separate values.

| Attribute | Safe value | Purpose | Class | Decision |
| --- | --- | --- | --- | --- |
| `url.path` | Inbound route template or outbound `/` | Preserve bounded operation grouping | Operational | Keep |
| `url.query` | Empty string | Overwrite any captured query string | Operational | Keep until exporter hooks can delete attributes |
| `url.full` | Inbound route template or outbound origin | Overwrite full request/dependency URLs | Operational | Keep for exporter compatibility |
| `http.target` | Same bounded path as `url.path` | Sanitize legacy instrumentation | Operational | Keep for compatibility |
| `http.url` | Same bounded value as `url.full` | Sanitize legacy instrumentation | Operational | Keep for compatibility |
| `http.response.status_code` | Integer HTTP status | Diagnose bounded upstream and verification failures | Operational | Keep |
| `status_code` | Integer HTTP status | Duplicate non-semantic status field | Operational | Rename to `http.response.status_code` |

The application does not add an actor, user, or session identifier to request
telemetry. A pseudonymous actor for the sensitive-route alert is a separate
privacy decision owned by #765.

## Error attributes

| Current attribute | Canonical attribute | Purpose | Cardinality | Class | Decision |
| --- | --- | --- | --- | --- | --- |
| `error.type` | `error.type` | Bounded failure category or exception class | Bounded code/class set | Operational | Keep |
| `error_type` | `error.type` | Duplicate error category | Bounded code/class set | Operational | Rename |
| `failure_kind` | `verification.failure.kind` | Classify Durable API failures | Fixed enum | Operational | Rename |
| `reason` | Event-specific dotted field | Explain a bounded configuration outcome | Fixed enum | Operational | Rename where the meaning is domain-specific |
| `error` | None | Raw exception string from a GitHub request | Uncontrolled | Prohibited | Remove; emit bounded `error.type` |
| `hint` | None | Constant human-readable startup advice | Fixed string | Operational | Remove; the event and runbook carry the guidance |

`logger.exception` is reserved for unexpected failures at an application
boundary. Expected or handled failures use a bounded category without raw
exception text. Exception alerts and incident notes must not include learner
input or provider response bodies.

## Verification attributes

`verification.attempt.id` is an opaque UUID used to correlate the API,
verification Functions, Durable status, and the persisted attempt row during
authorized incident response. It is linkable through the production database,
so it is retained only for the workspace retention period, is not included in
alert notifications, and must not be added to general request spans.

| Current attribute | Canonical attribute | Purpose | Cardinality | Class | Decision |
| --- | --- | --- | --- | --- | --- |
| `verification.attempt.id` | `verification.attempt.id` | Cross-system attempt correlation | One UUID per attempt | Linkable | Keep on verification lifecycle events |
| `attempt_id` | `verification.attempt.id` | Duplicate attempt correlation | One UUID per attempt | Linkable | Rename; never emit both |
| `user_id` | None | Database learner identity | One value per learner | Prohibited | Remove |
| `requirement_slug` | `verification.requirement.slug` | Identify the verifier/rubric involved | Bounded curriculum set | Learner activity | Rename |
| `verification.task.id` | `verification.task.id` | Identify a fixed verification task | Bounded curriculum set | Learner activity | Keep |
| `verification.check.name` | `verification.check.name` | Identify a registered check implementation | Bounded code set | Operational | Keep |
| `verification.step.result` | `verification.step.result` | Record `passed`, `failed`, `unavailable`, or `error` | Fixed enum | Learner activity | Keep |
| `verification.outcome` | `verification.outcome` | Persisted final attempt outcome | Fixed enum | Learner activity | Keep |
| `outcome` | `verification.outcome` | Duplicate final outcome | Fixed enum | Learner activity | Rename |
| `verification.error.code` | `verification.error.code` | Persisted safe failure code | Fixed enum | Operational | Keep |
| `error_code` | `verification.error.code` | Duplicate safe failure code | Fixed enum | Operational | Rename |
| `verification.terminal.source` | `verification.terminal.source` | Component that finalized an attempt | Fixed enum | Operational | Keep |
| `terminal_source` | `verification.terminal.source` | Duplicate terminal source | Fixed enum | Operational | Rename |
| `verification.failure.stage` | `verification.failure.stage` | Workflow stage that failed | Fixed enum | Operational | Keep |
| `verification.failure.kind` | `verification.failure.kind` | Durable/client failure category | Fixed enum | Operational | Keep after rename |
| `runtime_status` | `verification.durable.status` | Durable runtime state observed by the API | Fixed Durable enum | Operational | Rename |
| `durable_status` | `verification.durable.status` | Duplicate Durable runtime state | Fixed Durable enum | Operational | Rename |
| `stuck_reason` | `verification.stuck.reason` | Why an attempt is considered stuck | Fixed enum | Operational | Rename |
| `attempt_age_seconds` | `verification.attempt.age_seconds` | Age of a confirmed stale attempt | Numeric | Operational | Rename |
| `attempt_created` | `verification.attempt.created` | Whether submission created a new attempt | Boolean | Operational | Rename |
| `cas_won` | `verification.terminal.write_won` | Whether compare-and-set finalized the attempt | Boolean | Operational | Rename |
| `orchestrator_name` | None | Duplicates platform Durable task name | Fixed value | Operational | Remove |
| `verification.operation` | `verification.operation` | Bounded deployed-API operation template | Fixed code set | Learner activity | Keep |
| `verification.reason` | `verification.reason` | Bounded verification decision reason | Fixed enum | Learner activity | Keep |
| `deployed_api.challenge_verified` | `verification.deployed_api.challenge_verified` | Ownership challenge passed | Boolean | Learner activity | Rename |
| `deployed_api.verified` | `verification.deployed_api.verified` | Core API contract passed | Boolean | Learner activity | Rename |
| `deployed_api.ai_verified` | `verification.deployed_api.ai_verified` | AI endpoint contract passed | Boolean | Learner activity | Rename |

### Reconciler summary attributes

| Current attribute | Canonical attribute | Purpose | Cardinality | Class | Decision |
| --- | --- | --- | --- | --- | --- |
| `candidate_count` | `verification.reconciler.candidate_count` | Attempts inspected in one scan | Numeric | Operational | Rename |
| `terminalized_count` | `verification.reconciler.terminalized_count` | Attempts finalized in one scan | Numeric | Operational | Rename |
| `stuck_count` | `verification.reconciler.stuck_count` | Active attempts still beyond the limit | Numeric | Operational | Rename |
| `cutoff` | None | Exact scan cutoff timestamp | One value per scan | Operational, high-cardinality | Remove; `timestamp` and configured window are sufficient |

## Content and startup attributes

| Current attribute | Canonical attribute | Purpose | Cardinality | Class | Decision |
| --- | --- | --- | --- | --- | --- |
| `curriculum_version` | `content.curriculum.version` | Identify loaded curriculum release | One per content release | Operational | Rename |
| `artifact_schema_version` | `content.artifact_schema.version` | Identify compiled artifact schema | One per schema release | Operational | Rename |
| `content_hash` | `content.artifact.hash` | Correlate startup with exact compiled content | One per content build | Operational | Rename |
| `topic_slug` | `content.topic.slug` | Identify invalid bundled topic | Bounded curriculum set | Operational | Rename |
| `requirement_slug` on content events | `content.requirement.slug` | Identify invalid bundled requirement | Bounded curriculum set | Operational | Rename |
| `phase_slug` | `content.phase.slug` | Identify invalid bundled phase | Bounded curriculum set | Operational | Rename |
| `path` | None | Absolute or repository content path | Uncontrolled string | Operational, high-cardinality | Remove; the slug identifies the artifact |
| `db_head` | `database.schema.current_revision` | Identify the database migration revision | One per migration | Operational | Rename |
| `code_head` | `database.schema.expected_revision` | Identify the deployed code migration revision | One per migration | Operational | Rename |
| `init_done` | `startup.initialized` | Distinguish timeout before initialization | Boolean | Operational | Rename |

## Community and authentication attributes

| Current attribute | Canonical attribute | Purpose | Cardinality | Class | Decision |
| --- | --- | --- | --- | --- | --- |
| `repo` | `github.repository` | Identify a failed curriculum repository lookup | Fixed public repository set | Operational | Rename; only approved curriculum repositories |
| `status_code` on auth events | `http.response.status_code` | GitHub OAuth response status | Bounded integer | Operational | Rename |
| `reason` on auth events | `auth.configuration.reason` | Explain disabled OAuth | Fixed enum | Operational | Rename |
| `auth.identity.reason` | `auth.identity.reason` | Explain rejected session or provider identity | Fixed enum below | Operational | Keep |

Authentication telemetry never includes GitHub usernames, GitHub IDs, internal
user IDs, OAuth tokens, claims, or session identifiers.

`auth.session.identity_rejected` and `auth.callback.identity_rejected` are
warning-level logs for handled identity rejection. Their only application
attribute is `auth.identity.reason`:

| Value | Meaning |
| --- | --- |
| `incomplete_identity` | A session contains only one application identity field. |
| `invalid_user_id` | The ID fails the strict positive signed-64-bit integer contract. |
| `invalid_github_username` | The username fails the type, nonblank, length, or storage-encoding contract, including after OAuth normalization. |
| `invalid_response_format` | The provider response has invalid JSON/character encoding or is not a JSON object. |

These events replace the callback's former `auth.callback.missing_github_id`
and `auth.callback.missing_github_login` events. Existing provider transport
failures retain `auth.callback.profile_fetch_failed` and bounded `error.type`.

Rejection does not attach exception details or identity values. Empty sessions,
OAuth-state-only sessions, and cookies rejected by middleware do not produce
identity warnings. Cleaning an invalid session prevents another warning when
that cleaned session is read again; this is not cross-request deduplication if
a client keeps replaying the original cookie.

Handled rejection keeps the normal public-page 200, protected API/HTMX 401, and
browser 303 request telemetry. An invalid or mismatched persisted OAuth identity
after validated input is instead an internal invariant failure. It reaches
the existing `unhandled.exception` boundary with a fixed identity-free message,
not an additional identity-rejection warning. Never suppress that failure to
make authentication telemetry look healthy.

## Metrics

| Metric | Attribute | Purpose | Cardinality | Class | Decision |
| --- | --- | --- | --- | --- | --- |
| `github.api_error` | `error.type` | Count network, authentication, authorization, rate-limit, client, and provider failures | Fixed category set | Operational | Keep metric; replace mixed numeric/string `status` with bounded categories |

Metrics must use low-cardinality dimensions. Attempt IDs, routes with concrete
identifiers, repository names outside the approved curriculum set, exception
classes from arbitrary plugins, and learner-controlled values are not metric
dimensions.

## Browser telemetry

The browser intentionally records only query-free, bounded navigation and
transport signals. Cookies, local/session storage, automatic route tracking,
Ajax tracking, and Fetch tracking remain disabled.

| Signal/property | Purpose | Class | Decision |
| --- | --- | --- | --- |
| Page view name | Page title grouping | Learner activity | Keep |
| Page view URI | Navigation grouping | Learner activity | Replace concrete pathname with a bounded page family or route template; never include query or fragment |
| `navigationType` | Distinguish HTMX navigation | Operational | Rename to `navigation.type` |
| `method` | HTTP method for an HTMX transport failure | Operational | Rename to `http.request.method` |
| `boosted` | Whether HTMX boost initiated the request | Operational | Rename to `htmx.boosted` and keep as a boolean |
| `path` | Historical HTMX request path | Uncontrolled learner-facing route | Prohibited | Already removed; contract test must prevent return |
| `statusCode` | Historical duplicate failure status | Integer | Operational | Already removed; backend request telemetry owns server-visible status |
| Automatic exception `url` | Concrete browser URL | Uncontrolled | Prohibited | Disable or sanitize automatic browser exception collection |
| Automatic exception `message` | Browser exception text | Uncontrolled | Prohibited | Disable or replace with a bounded custom category |
| `refUri` | Browser SDK referrer URL | Uncontrolled external/internal URL | Prohibited | Remove with a telemetry initializer or disable the producing feature |
| `duration` | Browser SDK page-view timing | Numeric | Operational | Keep |

The frontend Application Insights resource must not be used to recreate a
learner session. Session cookies, SDK cookies, storage-backed identifiers,
authenticated user context, and pseudonymous user IDs remain disabled.

## Event names

Event names use lowercase dotted domains, for example
`verification.attempt.created`, `health.ready.schema_drift`, and
`telemetry.configure.failed`.

Existing underscore event names in shared verification code, such as
`deployed_api_timeout`, `fork_check_failed`, and `token_verification_succeeded`,
must be renamed to dotted domains when their producers are normalized. Event
names are bounded code constants and never contain learner values.

The following event families are retained:

- `auth.*`: OAuth configuration, bounded callback outcomes, and identity rejection.
- `content.*`: failures loading bundled curriculum artifacts.
- `db.*`: database lifecycle and rollback failures.
- `health.*`: readiness and schema drift signals.
- `init.*` and `telemetry.*`: startup and instrumentation state.
- `verification.*`, `ci.*`, `codeql.*`, `ghcr.*`, and `deployed_api.*`:
  bounded verification operations and outcomes.
- `github.*` and `token.*`: bounded GitHub and signed-token verification
  outcomes.
- `community.*`: fixed curriculum repository integration failures.
- `unhandled.exception`: the final API exception boundary.
- `user.account_deleted`: aggregate account-deletion completion without user
  identity.

## Production consumer audit

Audit performed on 2026-09-03 against the production-serving `dev`
environment:

- Terraform defines the backend and frontend Application Insights resources,
  shared Log Analytics workspace, availability web test, action group, and
  alert rules.
- Repository-managed KQL consumers are in `infra/monitoring.tf` and
  `docs/runbooks/alerts.md`.
- No custom Azure Workbooks or portal dashboards were present.
- The Log Analytics workspace contained only Azure-provided saved searches;
  no application-specific saved query was present.
- Seven days of production property names were inventoried without retrieving
  property values. The inventory confirmed current aliases and prohibited
  fields described above, plus SDK-owned Durable Functions, Functions,
  OpenTelemetry, and generative-AI properties.

Repeat this audit after producer changes deploy and before removing an alias
from a query. Historical rows can retain old fields until workspace retention
expires; verification must filter to the new deployment revision or deployment
time.

## Enforcement

Contract tests must:

- enumerate the exact application-owned fields explicitly emitted by Python
  logs, span attributes/events, metrics, and browser events;
- fail on aliases marked rename/remove and every prohibited identity or raw
  text field;
- verify request and dependency URL sanitization;
- verify browser telemetry cannot send query strings, concrete identifier
  paths, referrer URLs, or uncontrolled exceptions;
- verify Terraform alert KQL and runbook examples use canonical fields; and
- avoid freezing platform-owned SDK attributes.
