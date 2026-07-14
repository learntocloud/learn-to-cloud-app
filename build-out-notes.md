# Build-out Notes

## PR 4: Durable start idempotency

The plan assumed the fixed attempt UUID was enough to make Durable starts
idempotent. The Azure Durable Python SDK documents that `start_new` can replace
an existing instance with the same ID, so the bridge now first claims
`verification_attempts.started_at` with a database compare-and-set. Only the
claim winner calls `start_new`; retries inspect the existing instance and never
restart it.

The fixed instance ID, attempt lifecycle, and final schema remain unchanged.
