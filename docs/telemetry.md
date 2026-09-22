# Telemetry

Use OpenTelemetry/Application Insights for request/dependency timing,
correlation, and unexpected exception diagnostics. Add application events for
meaningful actions and saved outcomes, not copies of SDK signals.
Completion events must describe committed outcomes, not attempted writes.

## Data boundaries

Telemetry explains what happened; the database holds submissions and feedback.
Use operation and attempt IDs for authorized investigation, not metric dimensions.
Do not deliberately attach credentials, cookies, submitted bodies, fetched
source, profile values, or model prompts/results to logs or spans.

Keep SQL parameter hiding and credential-query URL filters. Native exception
diagnostics remain useful and can contain public profile values or arbitrary
error text; do not promise universal redaction or add custom profile-exception
rewriting. Tokens, cookies, and credentials must remain protected.
Expected provider failures use bounded categories; do not suppress unrelated
programming errors or convert them into learner failures.

## Avoid duplicate instrumentation

Azure Monitor owns production FastAPI instrumentation; local OTLP configures
it explicitly. Both HTTP and background verification use the same API role and
pipeline. Do not replace the SDK setup merely to remove default ASGI spans.
See the shared
[`observability configuration`](https://github.com/learntocloud/learn-to-cloud-app/blob/main/packages/learn-to-cloud-shared/src/learn_to_cloud_shared/core/observability.py).

Browser telemetry disables cookies and browser storage. HTMX hooks record page
views because SDK history tracking counts its replace/push navigation twice;
do not enable both mechanisms. Keep browser payload filtering in
[`frontend-telemetry.js`](https://github.com/learntocloud/learn-to-cloud-app/blob/main/api/src/learn_to_cloud/static/js/frontend-telemetry.js).

## Changing signals

Preserve event names and fields consumed by alerts. Review changes together with
[`monitoring.tf`](https://github.com/learntocloud/learn-to-cloud-app/blob/main/infra/monitoring.tf),
the [alert runbook](runbooks/alerts.html), and
[`telemetry contract tests`](https://github.com/learntocloud/learn-to-cloud-app/blob/main/api/tests/test_telemetry_contracts.py).
Keep those executable contracts authoritative instead of maintaining a separate
field registry.
