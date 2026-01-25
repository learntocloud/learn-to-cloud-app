# Content Strategy

This document explains how course content is structured, served, and updated in the Learn to Cloud application.

## Architecture Overview

Content (phases, topics, questions) lives in a single location and is consumed by both the frontend and API:

```
frontend/public/content/phases/
├── phase0/
│   ├── index.json              # Phase metadata
│   ├── cloud-computing.json    # Topic content
│   └── ...
├── phase1/
├── phase2/
└── ...
```

### Why Both Frontend and API Need Content

| Component | What It Uses Content For |
|-----------|-------------------------|
| **Frontend** | Display: topic text, learning steps, question prompts, scenario generation |
| **API** | Validation & grading: verify IDs exist, get `grading_rubric` and `concepts` for LLM grading, generate scenario questions |

The API cannot trust the client to send grading criteria—that would allow cheating. So the API maintains its own copy of content for server-side validation.

## How Content Is Served

### Frontend (Azure Static Web Apps)

- Content JSON files are served directly from the CDN at `/content/phases/...`
- The frontend fetches content at runtime via `fetch('/content/phase0/cloud-computing.json')`
- Fast, cached at edge locations globally

### API (Azure Container Apps)

- Content is **copied into the Docker image** at build time
- See [api/Dockerfile](../api/Dockerfile) lines 53-56:
  ```dockerfile
  ENV CONTENT_DIR="/app/content/phases"
  COPY --chown=appuser:appuser frontend/public/content /app/content
  ```
- The API loads content once at startup and caches it in memory
- No runtime dependency on the frontend CDN

### Local Development

- API reads directly from `frontend/public/content/phases/` (no copy needed)
- Both frontend and API see the same files immediately

## Content Structure

### Phase Index (`phase0/index.json`)

```json
{
  "id": "phase0",
  "slug": "phase0",
  "name": "Phase 0: Getting Started",
  "description": "Begin your cloud journey",
  "order": 0,
  "topics": [
    {
      "slug": "cloud-computing",
      "name": "Introduction to Cloud Computing",
      "order": 1
    }
  ]
}
```

### Topic Content (`phase0/cloud-computing.json`)

```json
{
  "id": "phase0-cloud-computing",
  "slug": "cloud-computing",
  "name": "Introduction to Cloud Computing",
  "description": "Learn the fundamentals of cloud computing",
  "order": 1,
  "estimated_time": "30 minutes",
  "is_capstone": false,
  "learning_objectives": [
    { "id": "lo1", "text": "Define cloud computing", "order": 1 }
  ],
  "learning_steps": [
    {
      "order": 1,
      "text": "Read this introduction to cloud computing",
      "action": "read",
      "title": "What is Cloud Computing?",
      "url": "https://example.com/article",
      "description": "A comprehensive overview..."
    }
  ],
  "questions": [
    {
      "id": "phase0-cloud-computing-q1",
      "prompt": "What are the main characteristics of cloud computing?",
      "scenario_seeds": [
        "A startup is evaluating whether to use cloud services instead of buying servers",
        "Your CEO asks you to explain why the company should migrate to the cloud",
        "During an interview, you're asked to compare cloud computing to traditional IT"
      ],
      "grading_rubric": "Answer must explain on-demand access AND scalability AND the pay-as-you-go model",
      "concepts": {
        "required": ["on-demand", "scalable"],
        "expected": ["pay-as-you-go", "internet-accessible"],
        "bonus": ["elasticity", "measured service", "resource pooling"]
      }
    }
  ]
}
```

### Question Schema

Each question uses scenario-based grading to test applied understanding rather than memorization:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | Yes | Unique identifier (format: `{phase}-{topic}-q{n}`) |
| `prompt` | string | Yes | The base question text shown to users |
| `scenario_seeds` | string[] | Yes | 3 scenario contexts for dynamic question generation |
| `grading_rubric` | string | Yes | Human-readable criteria for passing (e.g., "Must explain X AND Y") |
| `concepts` | object | Yes | Structured concept categories for grading |
| `concepts.required` | string[] | Yes | Core concepts that MUST be addressed for passing |
| `concepts.expected` | string[] | Yes | Important concepts that should be included |
| `concepts.bonus` | string[] | Yes | Advanced concepts that demonstrate deeper understanding |

**How Scenario Questions Work:**
1. User requests a question → API generates a unique scenario using one of the `scenario_seeds`
2. The scenario is cached per user/question for 1 hour
3. User's answer is graded against the `grading_rubric` with concept awareness
4. On LLM failure, the base `prompt` is shown as fallback

## Deployment Workflows

### Content-Only Changes

When you **only** modify files in `frontend/public/content/`:

1. **Workflow triggered**: `deploy-content.yml`
2. **What happens**: Frontend rebuilds and deploys to Azure Static Web Apps
3. **Duration**: ~30 seconds
4. **API impact**: None (API keeps old content until next full deploy)

### Code or Structural Changes

When you modify API code, frontend code, or add new phases/topics:

1. **Workflow triggered**: `deploy.yml`
2. **What happens**: Full build—API Docker image + frontend
3. **Duration**: 3-5 minutes
4. **API impact**: Gets fresh content copy

## How to Update Content

### Edit Existing Content (Text Changes)

**Example**: Fix a typo, update a URL, reword a question prompt

1. Edit the JSON file in `frontend/public/content/phases/`
2. Commit and push to `main`
3. `deploy-content.yml` triggers automatically
4. Changes live in ~30 seconds

```bash
# Example: Update a resource URL in phase 1
vim frontend/public/content/phases/phase1/cli-basics.json
git add -A && git commit -m "Update Linux tutorial link"
git push origin main
```

> **Note**: If you change grading criteria (`grading_rubric`, `concepts`), the API won't pick up the change until a full deploy. Consider triggering a manual full deploy if grading criteria change.

### Add a New Question to Existing Topic

1. Edit the topic's JSON file
2. Add the question to the `questions` array:
   ```json
   {
     "id": "phase1-cli-basics-q3",
     "prompt": "What command lists files in a directory?",
     "scenario_seeds": [
       "You SSH into a new server and need to explore what files are present",
       "A coworker asks you to verify a file exists in their home directory",
       "Your deployment script needs to check directory contents before proceeding"
     ],
     "grading_rubric": "Must identify ls command AND explain it shows directory contents",
     "concepts": {
       "required": ["ls"],
       "expected": ["list", "directory contents"],
       "bonus": ["flags like -l", "hidden files with -a"]
     }
   }
   ```
3. Commit and push to `main`
4. **Important**: Trigger a full deploy so the API knows about the new question:
   - Go to GitHub Actions → `Deploy to Azure` → Run workflow

### Add a New Topic to Existing Phase

1. Create the topic JSON file:
   ```bash
   touch frontend/public/content/phases/phase1/new-topic.json
   ```

2. Add topic content (use existing topic as template)

3. Update the phase's `index.json` to include the new topic:
   ```json
   {
     "topics": [
       { "slug": "existing-topic", "name": "...", "order": 1 },
       { "slug": "new-topic", "name": "New Topic Name", "order": 2 }
     ]
   }
   ```

4. Commit and push to `main`

5. Trigger full deploy (new topic = structural change)

### Add a New Phase

1. Create the phase directory:
   ```bash
   mkdir frontend/public/content/phases/phase7
   ```

2. Create `index.json` for the phase:
   ```json
   {
     "id": "phase7",
     "slug": "phase7",
     "name": "Phase 7: Advanced Topics",
     "description": "Deep dive into advanced cloud concepts",
     "order": 7,
     "topics": []
   }
   ```

3. Add topic JSON files to the phase directory

4. Update `index.json` with topic references

5. Commit and push to `main`

6. Full deploy triggers automatically (structural change)

## Content Validation

The API validates content at startup. If content is malformed:
- API logs errors but continues running
- Invalid topics/questions will fail when accessed

To validate content locally before pushing:

```bash
cd api
uv run python -c "from services.content_service import get_all_phases; print(f'Loaded {len(get_all_phases())} phases')"
```

## Frequently Asked Questions

### Do I need to rebuild the API for text changes?

**No**, but with a caveat:
- Frontend will show updated text immediately after `deploy-content.yml` completes
- API won't have the new text until next full deploy
- This usually doesn't matter unless the API returns content text (it mostly just validates IDs and grades answers)

### What if I change grading criteria?

The API uses `grading_rubric` and `concepts` for LLM grading. If you change these:
1. Push your changes
2. Manually trigger `Deploy to Azure` workflow to rebuild the API
3. Otherwise, grading will use old criteria until the next full deploy

### Can content get out of sync between frontend and API?

Yes, temporarily:
- After a content-only deploy, frontend has new content, API has old
- This is usually fine—API validates IDs that exist in both versions
- Adding **new** questions/topics without an API deploy means API will reject them as "unknown"

### How do I force a full deploy?

1. Go to GitHub → Actions → `Deploy to Azure`
2. Click "Run workflow"
3. Optionally check "Force rebuild without cache"

## Design Decisions

### Why copy content into the API Docker image?

**Alternatives considered:**
1. API fetches from frontend CDN at startup
2. Separate grading requirements from display content
3. Store content in database

**We chose embedding because:**
- Simple and reliable—no runtime dependencies
- Content is small (few KB of JSON)
- Monthly update frequency doesn't justify complexity
- API works even if CDN is down

### Why not a CMS?

For our scale (small team, monthly updates), Git-based content management is simpler:
- Version control built-in
- PR review process for changes
- No additional service to manage
- Free

If we onboard non-technical content editors in the future, we'd reconsider.
