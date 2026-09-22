# Architecture

The API serves HTML and JSON and runs background verification. PostgreSQL owns
accounts, sessions, and learner state; the packaged curriculum catalog owns
content. See [Curriculum architecture](curriculum.html),
[Authentication and sessions](authentication.html), and [Telemetry](telemetry.html).

## Where changes belong

Routes handle HTTP and dependency injection; services coordinate application
behavior; repositories own queries. Keep domain checks independent of HTTP.
The session lifecycle service also handles browser-cookie cleanup.

Prepare template data in
[`rendering/`](https://github.com/learntocloud/learn-to-cloud-app/tree/main/api/src/learn_to_cloud/rendering).
These helpers are synchronous and perform no database or network I/O. Reuse
their feedback and display builders rather than formatting the same outcome
differently on cards and history pages.

Submission rules live in
[`verification_forms.py`](https://github.com/learntocloud/learn-to-cloud-app/blob/main/api/src/learn_to_cloud/verification_forms.py);
rendering consumes that contract instead of duplicating validation.

## Background verification

The API starts one sequential verification loop per process. PostgreSQL stores
pending attempts, and atomic claims prevent replicas from executing the same
attempt. There is no external queue or workflow engine.

An execution is bounded and never resumed or automatically replayed after a
crash. Overdue cleanup saves a terminal outcome so the learner can submit again.
Provider-level retries are separate from retrying an entire submission.
Do not manually unclaim work that may still be executing.

Both health endpoints reject a stopped worker, but a live task does not prove
that the queue is progressing. Use the
[active-attempt runbook](runbooks/alerts.html#verification-active-beyond-limit)
for backlog and worker failures.

For execution limits and claim behavior, consult
[`VerificationWorkerConfig`](https://github.com/learntocloud/learn-to-cloud-app/blob/main/packages/learn-to-cloud-shared/src/learn_to_cloud_shared/core/config.py)
and the
[`worker`](https://github.com/learntocloud/learn-to-cloud-app/blob/main/api/src/learn_to_cloud/services/verification_worker.py).

## Changing verification

Add checks to the shared
[`verification/checks/`](https://github.com/learntocloud/learn-to-cloud-app/tree/main/packages/learn-to-cloud-shared/src/learn_to_cloud_shared/verification/checks)
and compose them in
[`workflows.py`](https://github.com/learntocloud/learn-to-cloud-app/blob/main/packages/learn-to-cloud-shared/src/learn_to_cloud_shared/verification/workflows.py).
Keep orchestration and step telemetry in the engine, and provider error
classification in the integration that understands the response.
Extend check and workflow-contract tests together.

Preserve these distinctions:

- **Ownership:** repository checks compare GitHub's numeric owner ID with the
  trusted learner ID from the saved attempt. Never trust a browser-supplied owner
  ID or bypass the shared preflight. Ownership is not a commit-atomic snapshot.
- **Learner failure versus incomplete verification:** missing required work can
  fail an assignment; a GitHub outage or incomplete evidence must not. Preserve
  the saved cause in cards and history without inventing causes for older rows.
- **Complete evidence:** grade the entire selected packet or do not grade.
  Never truncate, summarize, drop optional files, or infer uncollected code to
  fit a budget. A selected file disappearing is not proof it was absent.
- **Unexpected failures:** let programming errors propagate. Native exception
  diagnostics are retained; expected provider failures use bounded categories.
  Do not turn cancellation into learner failure.

Required paths, rubric criteria, and evidence limits belong in
[`verification/tasks/`](https://github.com/learntocloud/learn-to-cloud-app/tree/main/packages/learn-to-cloud-shared/src/learn_to_cloud_shared/verification/tasks),
not a second documentation inventory. See the
[evidence runbook](runbooks/alerts.html#incomplete-grading-evidence) for recovery.

## Deployed API verification

The deployment probe creates one journal entry, then requests analysis of that
entry. It does not prove repository ownership or audit historical entries.
Neither POST is retried automatically: repeating mutations can create duplicate
learner data. Created entries remain even when analysis fails; the verifier
does not delete them.

Preserve HTTPS, private-target checks, disabled redirects, and request timeouts
when changing the
[`request boundary`](https://github.com/learntocloud/learn-to-cloud-app/blob/main/packages/learn-to-cloud-shared/src/learn_to_cloud_shared/verification/deployed_api.py).
Response-peer inspection cannot undo a request's side effects.

## Verification UI

Show server-confirmed states, not simulated progress. On completion, refresh the
whole workspace so unlocks and history agree with the result. Preserve checking
content between polls, animate only changed states, and respect reduced motion.
Keep the reload fallback and the Node-based transition tests when changing
[`verification.js`](https://github.com/learntocloud/learn-to-cloud-app/blob/main/api/src/learn_to_cloud/static/js/verification.js).
