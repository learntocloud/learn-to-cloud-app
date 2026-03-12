---
on:
  push:
    branches: [main]
    paths:
      - '.github/skills/**'
      - '.github/agents/**'
      - '.github/prompts/**'
      - '.github/workflows/**'
      - '.github/dependabot.yml'
      - 'AGENTS.md'
      - 'SECURITY.md'
      - '.devcontainer/**'
  workflow_dispatch:

description: >
  Keep the project's living slide deck (docs/scaling-with-github/index.html)
  in sync with the actual repo. Scans for skills, agents, prompts, and
  workflows, then opens a PR if the deck is out of date.

engine: copilot

steps:
  - name: Checkout repository
    uses: actions/checkout@v4

permissions:
  contents: write
  pull-requests: write

tools:
  github:
    toolsets: [repos, pull_requests]
  bash: ["cat", "find", "grep", "head", "tail", "wc", "echo", "sort", "ls", "sed", "awk", "basename", "dirname"]

safe-outputs:
  create-pull-request:
    title-prefix: "[deck-sync] "
    labels: [documentation, automation]
    close-older-pull-requests: true
---

# Update Living Deck

You are a documentation maintainer for the Learn to Cloud project. Your job is to ensure the slide deck at `docs/scaling-with-github/index.html` accurately reflects the current state of the repo's Copilot customizations, GitHub Actions workflows, and security configuration.

## Goal

Compare what exists in the repo against what's mentioned in the deck. If anything is missing, outdated, or refers to files that no longer exist, open a PR with the corrections.

## Process

### Step 1: Inventory what exists in the repo

Scan the repo to build a current inventory:

```bash
echo "=== SKILLS ==="
find .github/skills -name "SKILL.md" 2>/dev/null | sort

echo "=== AGENTS ==="
find .github/agents -name "*.agent.md" 2>/dev/null | sort

echo "=== PROMPTS ==="
find .github/prompts -name "*.prompt.md" 2>/dev/null | sort

echo "=== WORKFLOWS ==="
find .github/workflows -type f \( -name "*.yml" -o -name "*.md" \) ! -name "*.lock.yml" 2>/dev/null | sort

echo "=== DEPENDABOT ==="
ls .github/dependabot.yml 2>/dev/null

echo "=== SECURITY ==="
ls SECURITY.md 2>/dev/null

echo "=== AGENTS.MD ==="
ls AGENTS.md 2>/dev/null
```

For each skill, extract its name and description from the YAML frontmatter:

```bash
for f in $(find .github/skills -name "SKILL.md" | sort); do
  echo "--- $f ---"
  sed -n '/^---$/,/^---$/p' "$f" | head -10
done
```

### Step 2: Read the current deck

```bash
cat docs/scaling-with-github/index.html
```

### Step 3: Compare and identify gaps

Check for:

1. **Missing skills**: skills in the repo not mentioned in the deck's "All Our Skills" table
2. **Removed skills**: skills mentioned in the deck that no longer exist in the repo
3. **Missing agents**: agents in the repo not shown in the deck
4. **Missing prompts**: prompt files in the repo not mentioned
5. **Missing workflows**: workflows not listed in the Copilot Workflows table
6. **Wrong counts**: the "Compound Effect" slide has counts (skills, agents, prompts) — verify they match
7. **Wrong file paths**: file paths shown in slides that don't match actual locations
8. **Stale .github/ directory tree**: the recap slide shows a directory tree — verify it matches reality

### Step 4: If no changes needed, stop

If the deck is fully up to date with the repo, output "Deck is up to date" and stop. Do not create a PR.

### Step 5: If changes needed, update the deck

Edit `docs/scaling-with-github/index.html` to fix the identified gaps. Preserve the existing HTML structure and styling. Only modify content that is factually incorrect or incomplete.

Key rules:
- Keep the slide order and narrative flow intact
- Update the "All Our Skills" table to match actual skills
- Update the Copilot Workflows table to match actual workflows
- Update the .github/ directory tree to match reality
- Update the compound effect numbers to be accurate
- Do not change styling, colors, or layout
- Do not add explanatory slides for new items — just update tables and lists

### Step 6: Create a PR

Create a branch named `deck-sync/update-YYYY-MM-DD` and open a PR with:
- Title: "Sync deck with repo changes"
- Body: a summary of what changed (which skills/agents/workflows were added or removed)
