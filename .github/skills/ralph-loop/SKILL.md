---
name: ralph-loop
description: Run a Ralph Loop for iterative Python file review with worker/reviewer cycle. Use when user says "ralph loop" or "iterate on review" for exhaustive quality-gated analysis.
---

# Ralph Loop for Python Library Review

The Ralph Loop is an iterative development pattern that keeps working on a task until it's genuinely complete. It uses:

1. **Worker Agent** - Does the deep-dive review
2. **Reviewer Agent** - Reviews with fresh context and either approves or requests changes
3. **Loop continues** until the Reviewer approves

## Key Insight: Fresh Context Per Iteration

Each iteration starts with fresh context. State is preserved in files:
- `.ralph/state.md` - Current iteration, status
- `.ralph/output.md` - Worker's review output
- `.ralph/feedback.md` - Reviewer's feedback

This prevents context accumulation noise from failed attempts.

## How to Start a Ralph Loop

### Option 1: Using the Shell Script

```bash
./.github/scripts/ralph-loop.sh "api/repositories/submission_repository.py"
```

### Option 2: Manual CLI Invocation

```bash
# Initialize state
mkdir -p .ralph
echo "## Current State
- Iteration: 1
- Status: not_started
- File to review: api/repositories/submission_repository.py" > .ralph/state.md

# Run worker
copilot --agent=ralph-worker --prompt "Review the file specified in .ralph/state.md"

# Run reviewer
copilot --agent=ralph-reviewer --prompt "Review the worker output in .ralph/output.md"

# Check state and repeat if needed
cat .ralph/state.md
```

### Option 3: In VS Code Chat

1. Select a Python file
2. Use the `@ralph-worker` agent to start the review
3. After completion, use `@ralph-reviewer` to evaluate
4. If rejected, go back to `@ralph-worker` (it reads the feedback)
5. Repeat until approved

## State File Format

### `.ralph/state.md`
```markdown
## Current State
- Iteration: 3
- Status: approved | needs_work | work_complete
- File reviewed: api/repositories/submission_repository.py
- Decision: SHIP IT 🚀
```

### `.ralph/feedback.md`
```markdown
## Reviewer Feedback - Iteration 2

### Issues Found
1. SQLAlchemy upsert claim lacks citation

### Required Actions
- [ ] Fetch docs for on_conflict_do_update
- [ ] Add URL to claim about index_elements
```

## Customizing the Loop

### Change Max Iterations
```bash
RALPH_MAX_ITERATIONS=10 ./.github/scripts/ralph-loop.sh "file.py"
```

### Use Different Models
Edit the agent files to specify a `model:` in frontmatter:
```yaml
---
name: ralph-worker
model: claude-opus-4
---
```

## Cleanup

After the loop completes:
```bash
rm -rf .ralph/
```

Or keep it for audit trail.
