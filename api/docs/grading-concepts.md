# Grading Concepts System

## Overview

The grading concepts system securely stores expected answers for knowledge questions in the database, separate from the content served to users. This prevents users from seeing the answers by inspecting frontend content.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Content Files                                │
│           content/phases/*/topic.json                                │
│   ┌───────────────────────────────────────────────────────────┐     │
│   │  questions: [                                              │     │
│   │    { id, prompt, expected_concepts: [...] }  ← SOURCE     │     │
│   │  ]                                                         │     │
│   └───────────────────────────────────────────────────────────┘     │
└─────────────────────┬───────────────────────────────────────────────┘
                      │
         ┌────────────┴────────────┐
         ▼                         ▼
┌─────────────────────┐   ┌─────────────────────────────────────────┐
│  Frontend (SWA)     │   │  Database (PostgreSQL)                   │
│  /content/*.json    │   │  grading_concepts table                  │
│  ┌───────────────┐  │   │  ┌─────────────────────────────────────┐ │
│  │ questions: [  │  │   │  │ question_id | expected_concepts     │ │
│  │   { id,       │  │   │  │ ----------- | ---------------       │ │
│  │     prompt }  │  │   │  │ phase0-q1   | ["concept1", ...]     │ │
│  │ ]             │  │   │  └─────────────────────────────────────┘ │
│  └───────────────┘  │   │                                          │
│  (NO expected_      │   │  (expected_concepts stored securely)     │
│   concepts!)        │   │                                          │
└─────────────────────┘   └─────────────────────────────────────────┘
         │                         │
         │                         │
         ▼                         ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         API Service                                  │
│  QuestionsService.grade_answer()                                     │
│    1. Get expected_concepts from GradingConceptRepository            │
│    2. Call LLM with user answer + expected_concepts                  │
│    3. Return grading result                                          │
└─────────────────────────────────────────────────────────────────────┘
```

## Data Flow

### On Deploy (CI/CD Pipeline)

```
1. GitHub Actions workflow runs
2. API Container App is updated
3. Migrations run (RUN_MIGRATIONS_ON_STARTUP=true)
4. "Sync grading concepts" step executes:

   az containerapp exec \
     --name ca-ltc-api-dev \
     --resource-group rg-ltc-dev \
     --command "python -m cli sync-grading-concepts"

5. CLI reads content/*.json files from the container
6. Extracts question_id + expected_concepts
7. Upserts into grading_concepts table
```

### On Content Update

When content files change (new questions, updated concepts):

1. PR merged to main
2. Deploy workflow triggers
3. Sync step runs automatically
4. New/updated concepts are upserted into database

### On Answer Submission

```
User submits answer
       │
       ▼
┌─────────────────────────────────────┐
│  POST /v1/questions/{id}/answer     │
│  Body: { answer: "user's response" }│
└──────────────────┬──────────────────┘
                   │
                   ▼
┌─────────────────────────────────────┐
│  QuestionsService.grade_answer()    │
│    1. grading_repo.get_by_id(id)    │
│    2. → expected_concepts from DB   │
│    3. llm.grade(answer, concepts)   │
│    4. Return GradeResult            │
└─────────────────────────────────────┘
```

## Database Schema

```sql
CREATE TABLE grading_concepts (
    question_id      VARCHAR(100) PRIMARY KEY,
    expected_concepts JSONB NOT NULL,
    created_at       TIMESTAMPTZ NOT NULL,
    updated_at       TIMESTAMPTZ NOT NULL
);

-- Example data:
-- question_id: "phase0-topic1-q1"
-- expected_concepts: ["IaaS", "PaaS", "SaaS", "shared responsibility", ...]
```

## CLI Commands

### Sync Grading Concepts

```bash
# Local development
cd api
uv run python -m cli sync-grading-concepts

# Production (via Azure Container Apps)
az containerapp exec \
  --name ca-ltc-api-dev \
  --resource-group rg-ltc-dev \
  --command "python -m cli sync-grading-concepts"
```

### Run Migrations

```bash
# Local
uv run python -m cli migrate

# Or via alembic directly
uv run alembic upgrade head
```

## Files

| File | Purpose |
|------|---------|
| `models.py` | `GradingConcept` SQLAlchemy model |
| `repositories/grading_repository.py` | Database access for grading concepts |
| `services/questions_service.py` | Uses repository to get concepts for grading |
| `scripts/seed_grading_concepts.py` | Extract concepts from content, upsert to DB |
| `cli.py` | CLI entry point for sync command |
| `alembic/versions/add_grading_concepts_table.py` | Migration (creates table + initial seed) |

## Security Benefits

1. **Expected concepts never sent to frontend** - Users cannot inspect network traffic to see answers
2. **Content files stripped** - `prepare_frontend_content.py` removes `expected_concepts` before copying to frontend
3. **Database is single source of truth** - API always reads from secure database

## Adding New Questions

1. Add question to `content/phases/<phase>/<topic>.json`:
   ```json
   {
     "id": "phase1-topic2-q3",
     "prompt": "Explain the concept...",
     "expected_concepts": ["concept1", "concept2", "concept3"]
   }
   ```

2. Run the frontend content preparation:
   ```bash
   python scripts/prepare_frontend_content.py
   ```

3. Commit and push - the deploy workflow will:
   - Deploy new content to SWA (stripped of expected_concepts)
   - Sync grading concepts to database (with expected_concepts)

## Local Development

For local testing, seed the database manually:

```bash
# Start database
docker compose up db -d

# Run migrations
cd api && uv run alembic upgrade head

# Seed grading concepts
DATABASE_URL="postgresql://ltc_user:ltc_password@localhost:5432/learntocloud" \
  uv run python -m cli sync-grading-concepts
```
