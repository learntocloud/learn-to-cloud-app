---
on:
  schedule: daily around 5am ET
  workflow_dispatch:
permissions:
  contents: read
  issues: read
  pull-requests: read
tools:
  github:
    toolsets: [issues, pull_requests, repos]
safe-outputs:
  github-token: ${{ secrets.GH_AW_CROSS_REPO_PAT }}
  create-issue:
    title-prefix: "[issues-overview] "
    labels: [report, issues-overview]
    close-older-issues: true
---

# Cross-Repo Issues & PRs Overview

Generate a consolidated overview of open issues and pull requests across all learntocloud repositories, delivered as a GitHub issue in this repo.

## Repositories to scan

- `learntocloud/journal-starter`
- `learntocloud/networking-lab`
- `learntocloud/linux-ctfs`
- `learntocloud/learn-to-cloud-app`

## What to include

### Issues
For each repository, provide:

- Total count of open issues
- List of open issues with: issue number, title, labels, author, date opened, and link
- Flag any issues older than 14 days as "stale"
- Flag any issues with no labels as "needs triage"
- Flag any issues with no assignee as "unassigned"

### Pull Requests
For each repository, provide:

- Total count of open PRs
- List of open PRs with: PR number, title, author, date opened, draft status, review status, and link
- Flag any PRs older than 7 days as "needs attention"
- Flag any PRs with no reviewers assigned as "needs reviewer"
- Note if CI checks are failing

## Report format

Structure the report as a clean markdown issue with:

1. **Executive summary** — one-liner per repo (e.g. "networking-lab: 3 issues, 1 PR, 1 stale")
2. **Per-repo breakdown** — separate tables for issues and PRs, sorted by most recent first
3. **Action items** — list of issues and PRs needing attention (stale, unassigned, needs-triage, needs-reviewer)
4. **Trends** — if possible, compare to last report and note any changes

## Style

- Keep it concise and scannable
- Use tables for issue lists
- Use emoji for status indicators (🔴 stale, 🟡 needs-triage, ⚪ unassigned, ✅ healthy)
- Include direct links to each issue
