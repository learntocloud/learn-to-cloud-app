---
name: reset-prod-submissions
description: Reset verification submissions for a user in production. Use when user says "reset prod submissions", "reset phase X in prod", "undo prod verification", or "reset prod for <username>".
---

# Reset Production Submissions

Use this skill to delete submission records and reset phase progress counters in the **production** database.

## When to Use

- User asks to reset a phase verification in prod
- User asks to undo prod submissions for a specific user
- User wants to re-run verification for a specific phase in production

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

Before deleting, show what will be removed:

```bash
psql -h psql-ltc-dev-8v4tyz.postgres.database.azure.com -d learntocloud -U "$PG_USER" \
  --set=sslmode=require -P pager=off \
  -c "SELECT id, phase_id, requirement_id, submission_type, is_validated, attempt_number, created_at
      FROM submissions
      WHERE user_id = <USER_ID> AND phase_id = <PHASE_ID>
      ORDER BY created_at;" | cat
```

Also check the current progress counter:

```bash
psql -h psql-ltc-dev-8v4tyz.postgres.database.azure.com -d learntocloud -U "$PG_USER" \
  --set=sslmode=require -P pager=off \
  -c "SELECT * FROM user_phase_progress WHERE user_id = <USER_ID> AND phase_id = <PHASE_ID>;" | cat
```

## Step 5: Confirm with User

**Always ask for confirmation** before deleting. Show the number of rows and what phase is being reset.

## Step 6: Delete and Reset

Run as a single transaction:

```bash
psql -h psql-ltc-dev-8v4tyz.postgres.database.azure.com -d learntocloud -U "$PG_USER" \
  --set=sslmode=require -P pager=off \
  -c "
BEGIN;
DELETE FROM submissions WHERE user_id = <USER_ID> AND phase_id = <PHASE_ID>;
UPDATE user_phase_progress SET validated_submissions = 0, updated_at = NOW()
  WHERE user_id = <USER_ID> AND phase_id = <PHASE_ID>;
COMMIT;
" | cat
```

### Resetting Specific Requirements Only

To reset only certain requirements within a phase instead of the whole phase:

```bash
psql -h psql-ltc-dev-8v4tyz.postgres.database.azure.com -d learntocloud -U "$PG_USER" \
  --set=sslmode=require -P pager=off \
  -c "
BEGIN;
DELETE FROM submissions
  WHERE user_id = <USER_ID> AND phase_id = <PHASE_ID>
    AND requirement_id IN ('<REQ_1>', '<REQ_2>');
UPDATE user_phase_progress
  SET validated_submissions = (
    SELECT COUNT(*) FROM submissions
    WHERE user_id = <USER_ID> AND phase_id = <PHASE_ID> AND is_validated = true
  ), updated_at = NOW()
  WHERE user_id = <USER_ID> AND phase_id = <PHASE_ID>;
COMMIT;
" | cat
```

## Step 7: Verify

Confirm the reset was successful:

```bash
psql -h psql-ltc-dev-8v4tyz.postgres.database.azure.com -d learntocloud -U "$PG_USER" \
  --set=sslmode=require -P pager=off \
  -c "SELECT COUNT(*) as remaining FROM submissions WHERE user_id = <USER_ID> AND phase_id = <PHASE_ID>;
      SELECT validated_submissions FROM user_phase_progress WHERE user_id = <USER_ID> AND phase_id = <PHASE_ID>;" | cat
```

## Known Users

| GitHub Username | User ID   |
|-----------------|-----------|
| madebygps       | 6733686   |

## Tables

`users` · `submissions` · `user_phase_progress`
