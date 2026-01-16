---
name: db-query
description: Query the Learn to Cloud PostgreSQL database directly using Azure AD authentication. Use when investigating data issues, checking user records, debugging duplicates, or running ad-hoc SQL queries on the production database.
---

# Database Query Skill

Query the Learn to Cloud PostgreSQL database using Azure CLI and Entra ID authentication.

## Prerequisites

1. Azure CLI installed and logged in: `az login`
2. Your account must be an Entra ID admin on the PostgreSQL server
3. psql client installed (via `brew install postgresql` on macOS)

## Setup (One-Time)

### Add yourself as database admin
```bash
# Get your Azure AD Object ID
MY_OBJECT_ID=$(az ad signed-in-user show --query id -o tsv)
MY_NAME=$(az ad signed-in-user show --query displayName -o tsv)

# Add as Entra admin (requires Owner/Contributor on resource group)
az postgres flexible-server microsoft-entra-admin create \
  --resource-group rg-ltc-dev \
  --server-name psql-ltc-dev-8v4tyz \
  --display-name "$MY_NAME" \
  --object-id "$MY_OBJECT_ID" \
  --type User
```

### Add firewall rule for your IP
```bash
MY_IP=$(curl -s ifconfig.me)
az postgres flexible-server firewall-rule create \
  --resource-group rg-ltc-dev \
  --name psql-ltc-dev-8v4tyz \
  --rule-name AllowMyIP \
  --start-ip-address "$MY_IP" \
  --end-ip-address "$MY_IP"
```

## Querying the Database

### Quick Query (Single Command)
```bash
# Set up connection variables
export PGPASSWORD=$(az account get-access-token --resource-type oss-rdbms --query accessToken -o tsv)
export PGHOST=psql-ltc-dev-8v4tyz.postgres.database.azure.com
export PGDATABASE=learntocloud
export PGUSER=$(az ad signed-in-user show --query displayName -o tsv)
export PGSSLMODE=require

# Run a query
psql -c "SELECT COUNT(*) FROM users;"
```

### Interactive Session
```bash
export PGPASSWORD=$(az account get-access-token --resource-type oss-rdbms --query accessToken -o tsv)
psql "host=psql-ltc-dev-8v4tyz.postgres.database.azure.com port=5432 dbname=learntocloud user=gwynethpena sslmode=require"
```

## Common Queries

### List all tables
```sql
SELECT table_name FROM information_schema.tables
WHERE table_schema = 'public' ORDER BY table_name;
```

### User lookup
```sql
-- By GitHub username
SELECT id, email, first_name, github_username, created_at
FROM users WHERE github_username = 'madebygps';

-- By user ID
SELECT * FROM users WHERE id = 'user_abc123';

-- By email
SELECT * FROM users WHERE email LIKE '%@example.com';
```

### Find duplicate github usernames
```sql
SELECT github_username, COUNT(*) as cnt
FROM users
WHERE github_username IS NOT NULL
GROUP BY github_username
HAVING COUNT(*) > 1;
```

### User progress summary
```sql
SELECT
    u.id,
    u.github_username,
    (SELECT COUNT(*) FROM submissions WHERE user_id = u.id) as submissions,
    (SELECT COUNT(*) FROM step_progress WHERE user_id = u.id) as steps,
    (SELECT COUNT(*) FROM user_activities WHERE user_id = u.id) as activities,
    (SELECT COUNT(*) FROM question_attempts WHERE user_id = u.id) as questions
FROM users u
WHERE u.github_username = 'madebygps';
```

### Recent activity
```sql
SELECT user_id, activity_type, activity_date, metadata
FROM user_activities
ORDER BY activity_date DESC
LIMIT 20;
```

### Submissions by phase
```sql
SELECT phase_id, requirement_id, status, validated_at
FROM submissions
WHERE user_id = 'user_abc123'
ORDER BY phase_id, created_at;
```

## Cleanup (After Done)

### Remove firewall rule
```bash
az postgres flexible-server firewall-rule delete \
  --resource-group rg-ltc-dev \
  --name psql-ltc-dev-8v4tyz \
  --rule-name AllowMyIP \
  --yes
```

## Database Schema Overview

| Table | Description |
|-------|-------------|
| `users` | User accounts (synced from Clerk) |
| `submissions` | Hands-on project submissions |
| `step_progress` | Step completion tracking |
| `question_attempts` | Quiz question attempts |
| `user_activities` | Activity log for streaks/heatmaps |

## Environment Info

- **Server**: `psql-ltc-dev-8v4tyz.postgres.database.azure.com`
- **Database**: `learntocloud`
- **Resource Group**: `rg-ltc-dev`
- **Auth**: Microsoft Entra ID (Azure AD) only, no password auth
