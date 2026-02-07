---
name: query-db
description: Query production PostgreSQL with Entra ID auth. Use for investigating users, debugging duplicates, or ad-hoc queries.
---

# Query Production Database

> **Note**: The hostname below may change if infrastructure is recreated. Get the current hostname from `cd infra && terraform output database_host` or Azure Portal.

## Connect

```bash
# Get token and connect (token expires in ~1hr)
export PGPASSWORD=$(az account get-access-token --resource-type oss-rdbms --query accessToken -o tsv)
psql "host=psql-ltc-dev-8v4tyz.postgres.database.azure.com dbname=learntocloud user=$(az ad signed-in-user show --query displayName -o tsv) sslmode=require"
```

## First-Time Setup

Add firewall rule for your IP:
```bash
az postgres flexible-server firewall-rule create \
  --resource-group rg-ltc-dev --name psql-ltc-dev-8v4tyz \
  --rule-name AllowMyIP --start-ip-address $(curl -s ifconfig.me) --end-ip-address $(curl -s ifconfig.me)
```

## Useful Queries

```sql
-- Find duplicate GitHub usernames
SELECT github_username, COUNT(*) FROM users
WHERE github_username IS NOT NULL
GROUP BY github_username HAVING COUNT(*) > 1;

-- User progress summary
SELECT u.github_username,
  (SELECT COUNT(*) FROM submissions WHERE user_id = u.id) as submissions,
  (SELECT COUNT(*) FROM step_progress WHERE user_id = u.id) as steps,
  (SELECT COUNT(*) FROM certificates WHERE user_id = u.id) as certificates
FROM users u WHERE u.github_username = 'USERNAME';

-- User's submissions by phase
SELECT phase_id, requirement_id, is_validated, validated_at
FROM submissions WHERE user_id = 'USER_ID' ORDER BY phase_id;

-- Recent submissions
SELECT s.phase_id, s.requirement_id, s.is_validated, s.created_at, u.github_username
FROM submissions s JOIN users u ON s.user_id = u.id
ORDER BY s.created_at DESC LIMIT 20;

-- User's certificates
SELECT verification_code, recipient_name, issued_at, phases_completed
FROM certificates WHERE user_id = 'USER_ID';

-- User's step progress
SELECT topic_id, phase_id, step_order, completed_at
FROM step_progress WHERE user_id = 'USER_ID' ORDER BY phase_id, step_order;
```

## Tables

`users` · `submissions` · `step_progress` · `certificates`
