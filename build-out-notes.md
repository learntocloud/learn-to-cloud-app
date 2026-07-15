# Build-out Notes

## PR 4: Durable start idempotency

The plan assumed the fixed attempt UUID was enough to make Durable starts
idempotent. The Azure Durable Python SDK documents that `start_new` can replace
an existing instance with the same ID, so the bridge now first claims
`verification_attempts.started_at` with a database compare-and-set. Only the
claim winner calls `start_new`; retries inspect the existing instance and never
restart it.

The fixed instance ID, attempt lifecycle, and final schema remain unchanged.

## PR 8: Legacy drain compatibility

The plan said to stop all `step_progress` writes while retaining the legacy
read fallback for a drain deployment. Those two actions conflict when a learner
unchecks a previously mirrored step: deleting only
`learner_step_completions` would let the stale `step_progress` row make the
step appear complete again.

PR 8 therefore stops legacy inserts immediately but temporarily deletes the
matching `step_progress` row when a learner unchecks a step. This delete-through
is observable and is removed with the fallback and mirror trigger in the
contract layer.

The plan also did not account for an old Durable orchestration completing after
attempt reads became authoritative. Its legacy submission could be persisted
while the matching `verification_attempts` row stayed active, then be
reconciled incorrectly as a server error. PR 8 bridges legacy-orchestrator
results into the matching attempt with the same compare-and-set finalization
used by the new path. A temporary database trigger and idempotent repair
migration also cover jobs written after the original point-in-time backfill or
during a rolling deployment. The old orchestration remains registered only for
the drain cohort. A terminally failed legacy job is deleted only after its
matching attempt is terminalized in the same transaction, so an old API replica
can retry without leaving authoritative state active. The attempt retains the
historical job UUID until the contract layer removes provenance columns.
Temporary insert, result-link, and delete triggers make those guarantees hold
for older replicas throughout the rolling deployment, not only for the new
application revision. A final idempotent repair terminalizes any active attempt
whose legacy job was deleted before the delete trigger became available.
