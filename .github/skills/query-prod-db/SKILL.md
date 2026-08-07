---
name: query-prod-db
description: Query production PostgreSQL with Entra ID authentication for user investigation and data debugging. Use for production database lookups or ad-hoc queries.
---

# Query Production Database

Default to read-only queries. Require Azure CLI authentication and discover the
current PostgreSQL host from Terraform output or Azure; never hard-code its
generated suffix.

Authenticate with an OSS RDBMS access token and the signed-in Entra principal:

```bash
export PGPASSWORD="$(az account get-access-token --resource-type oss-rdbms --query accessToken -o tsv)"
export PG_USER="$(az ad signed-in-user show --query displayName -o tsv)"
psql -h "$PG_HOST" -d learntocloud -U "$PG_USER" --set=sslmode=require -P pager=off
```

The current learner verification state is in `verification_attempts`, keyed by
`user_id` and `requirement_uuid`; step progress is in
`learner_step_completions`, keyed by `user_id` and `step_uuid`. Consult current
models or migrations before querying other columns.

Use bounded results and parameter-safe SQL. Never print tokens. For writes,
show the exact affected rows, explain rollback behavior, and obtain explicit
confirmation before executing a transaction.

If temporary firewall access is necessary, obtain confirmation before adding a
narrow rule for the current IP, record its name, and remove it after the query.
