---
name: reset-prod-submissions
description: Reset verification submissions for a user in production. Use when user says "reset prod submissions", "reset phase X in prod", "undo prod verification", or "reset prod for <username>".
---

# Reset Production Submissions

Use this skill to delete submission records and reset progress in the **production** database.

Progress is derived live from the `submissions` table, so there is no separate
counter to update. Submissions are keyed by `requirement_uuid` (there is no
`phase_id` column). The `verification_jobs` table has a foreign key
(`fk_verification_jobs_result_submission_id`) pointing at `submissions.id`, so
you must delete a user's verification jobs **before** deleting their
submissions, or the delete will fail.

## When to Use

- User asks to reset verification in prod (a single requirement, or everything)
- User asks to undo prod submissions for a specific user
- User wants to re-run verification in production

## Prerequisites

Requires Azure CLI auth with access to the `rg-ltc-dev` resource group and Entra ID token for PostgreSQL.

## Step 1: Ensure Firewall Access

If the connection is refused, add a firewall rule for the current IP:

```bash
MY_IP=$(curl -s ifconfig.me)
az rest --method put \
  --url "https://management.azure.com/subscriptions/$(az account show --query id -o tsv)/resourceGroups/rg-ltc-dev/providers/Microsoft.DBforPostgreSQL/flexibleServers/psql-ltc-dev-8v4tyz/firewallRules/AllowDevContainer?api-version=2022-12-01" \
  --body "{\"properties\":{\"startIpAddress\":\"$MY_IP\",\"endIpAddress\":\"$MY_IP\"}}"
```

Wait ~30 seconds for the rule to propagate before connecting.

## Step 2: Connect

```bash
export PGPASSWORD=$(az account get-access-token --resource-type oss-rdbms --query accessToken -o tsv)
export PG_USER=$(az ad signed-in-user show --query displayName -o tsv)
```

> **Agent usage**: Always use `-P pager=off` and pipe through `| cat` to avoid blocking.

The hostname is `psql-ltc-dev-8v4tyz.postgres.database.azure.com`, database `learntocloud`.
If it changes, find the current one with: `az resource list --resource-group rg-ltc-dev --resource-type "Microsoft.DBforPostgreSQL/flexibleServers" --query "[].name" -o tsv`

## Step 3: Look Up the User

```bash
psql -h psql-ltc-dev-8v4tyz.postgres.database.azure.com -d learntocloud -U "$PG_USER" \
  --set=sslmode=require -P pager=off \
  -c "SELECT id, github_username FROM users WHERE github_username = '<USERNAME>';" | cat
```

## Step 4: Preview Submissions

Before deleting, show what will be removed. To reset **everything** for a user,
omit the `requirement_uuid` filter:

```bash
psql -h psql-ltc-dev-8v4tyz.postgres.database.azure.com -d learntocloud -U "$PG_USER" \
  --set=sslmode=require -P pager=off \
  -c "SELECT id, requirement_uuid, is_validated, verification_completed, created_at
      FROM submissions
      WHERE user_id = <USER_ID>
      ORDER BY created_at;
      SELECT COUNT(*) AS total, COUNT(*) FILTER (WHERE is_validated) AS validated
      FROM submissions WHERE user_id = <USER_ID>;" | cat
```

To scope to a single requirement, add `AND requirement_uuid = '<REQUIREMENT_UUID>'`
to the `WHERE` clauses above.

Also check how many verification jobs the user has (these reference the
submissions and must be deleted too):

```bash
psql -h psql-ltc-dev-8v4tyz.postgres.database.azure.com -d learntocloud -U "$PG_USER" \
  --set=sslmode=require -P pager=off \
  -c "SELECT COUNT(*) FROM verification_jobs WHERE user_id = <USER_ID>;" | cat
```

## Step 5: Confirm with User

**Always ask for confirmation** before deleting. Show the number of submissions
(and validated count) and what is being reset.

## Step 6: Delete and Reset

Delete the user's verification jobs first, then their submissions, in a single
transaction. The job delete is required because of the foreign key from
`verification_jobs.result_submission_id` to `submissions.id`.

To reset **everything** for a user:

```bash
psql -h psql-ltc-dev-8v4tyz.postgres.database.azure.com -d learntocloud -U "$PG_USER" \
  --set=sslmode=require -P pager=off \
  -c "
BEGIN;
DELETE FROM verification_jobs WHERE user_id = <USER_ID>;
DELETE FROM submissions WHERE user_id = <USER_ID>;
COMMIT;
" | cat
```

### Resetting a Specific Requirement Only

To reset only one requirement instead of everything, scope both deletes by
`requirement_uuid`:

```bash
psql -h psql-ltc-dev-8v4tyz.postgres.database.azure.com -d learntocloud -U "$PG_USER" \
  --set=sslmode=require -P pager=off \
  -c "
BEGIN;
DELETE FROM verification_jobs
  WHERE user_id = <USER_ID> AND requirement_uuid = '<REQUIREMENT_UUID>';
DELETE FROM submissions
  WHERE user_id = <USER_ID> AND requirement_uuid = '<REQUIREMENT_UUID>';
COMMIT;
" | cat
```

## Step 7: Verify

Confirm the reset was successful:

```bash
psql -h psql-ltc-dev-8v4tyz.postgres.database.azure.com -d learntocloud -U "$PG_USER" \
  --set=sslmode=require -P pager=off \
  -c "SELECT COUNT(*) AS submissions_remaining FROM submissions WHERE user_id = <USER_ID>;
      SELECT COUNT(*) AS jobs_remaining FROM verification_jobs WHERE user_id = <USER_ID>;" | cat
```

## Known Users

| GitHub Username | User ID   |
|-----------------|-----------|
| madebygps       | 6733686   |

## Tables

`users` · `submissions` · `verification_jobs`
