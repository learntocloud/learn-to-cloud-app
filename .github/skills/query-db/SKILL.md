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
  (SELECT COUNT(*) FROM question_attempts WHERE user_id = u.id) as questions
FROM users u WHERE u.github_username = 'USERNAME';

-- Recent activity (for heatmap)
SELECT user_id, activity_type, activity_date
FROM user_activities ORDER BY activity_date DESC LIMIT 20;

-- User's submissions by phase
SELECT phase_id, requirement_id, status, validated_at
FROM submissions WHERE user_id = 'USER_ID' ORDER BY phase_id;
```

## Tables

`users` · `submissions` · `step_progress` · `question_attempts` · `user_activities`
