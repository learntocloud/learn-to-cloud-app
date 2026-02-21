---
on:
  schedule: weekly on sunday
  workflow_dispatch:

description: >
  Weekly report of community members who answered questions in GitHub Discussions
  or reported issues, so we can thank them in a social media post.

engine: copilot

steps:
  - name: Checkout repository
    uses: actions/checkout@v4

permissions:
  contents: read
  discussions: read
  issues: read

env:
  GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}

tools:
  github:
    toolsets: [repos]
    read-only: true
  bash: ["curl", "date", "gh", "python3"]

network:
  allowed:
    - defaults
    - github

safe-outputs:
  create-issue:
    title-prefix: "[community-thanks] "
    labels: [community, automation]
    close-older-issues: true
---

# Weekly Community Thanks

You are a community manager for the Learn to Cloud project.

## Goal

Create a weekly rollup of people who **answered questions** in GitHub Discussions **or reported issues** in this repository, so we can thank them in a weekly social media post.

## Definition: "Answered a question"

Treat a user as having answered a question if, during the last 7 days:

- They posted a **comment** on a Discussion in an **answerable (Q&A)** category, OR
- Their comment is marked as an **answer** (if available in the API / GraphQL schema).

Exclude:
- Bots (logins ending in `[bot]`, or accounts of type `BOT`).

## Process

### Step 1: Determine the time window

Use a rolling 7-day window from "now" (the workflow run time).

### Step 2: Fetch Q&A discussions and comments

Use `gh api graphql` to query the current repository's Discussions. The `GITHUB_TOKEN` environment variable is already set and `gh` will use it automatically.

Example:
```bash
gh api graphql -f query='query($owner:String!,$repo:String!){
  repository(owner:$owner,name:$repo){
    discussionCategories(first:10){ nodes{ id name isAnswerable } }
    discussions(first:50, orderBy:{field:UPDATED_AT, direction:DESC}){
      nodes{ number title url updatedAt
        comments(first:50){ nodes{ createdAt author{ login } } }
        answer{ createdAt author{ login } }
      }
    }
  }
}' -f owner='learntocloud' -f repo='learn-to-cloud-app'
```

High-level approach:
1. List discussion categories and identify which ones are **answerable** (Q&A).
2. For each answerable category, list discussions that were created or updated in the last 7 days.
3. For each discussion, fetch comments (and replies if applicable), then filter to comments created in the last 7 days.
4. Aggregate by `author.login`:
   - `answer_count`: number of qualifying comments in the window
   - `discussion_count`: number of unique discussions they participated in
   - `links`: a small set (up to 5) of discussion URLs they helped on

Be conservative with pagination: fetch enough items to cover typical weekly volume, and only add pagination if results are truncated.

### Step 3: Fetch issues opened in the last 7 days

Use `gh api` or `gh issue list` to list issues (not pull requests) created in the last 7 days.

Example:
```bash
gh issue list --repo learntocloud/learn-to-cloud-app --state all --json number,title,url,author,createdAt --limit 50
```

For each issue, record:
- `author.login`
- Issue number and URL
- Issue title

Aggregate by `author.login`:
- `issue_count`: number of issues opened in the window
- `links`: up to 5 issue URLs

Exclude:
- Pull requests (the Issues API may include PRs — filter them out).
- Bots (logins ending in `[bot]`, or accounts of type `BOT`).

### Step 4: Generate the report

If there are **no qualifying contributions** (no discussion answers AND no issues) in the last 7 days:
- Use the noop output: `"No community contributions in the last 7 days."`

Otherwise, create a GitHub issue with this structure:

```markdown
## Community Thanks — {date}

### 💬 Top discussion helpers (last 7 days)

| GitHub user | Answers | Discussions helped |
|------------|---------|--------------------|
| @user1 | 5 | 3 |
| @user2 | 2 | 2 |

### 🐛 Issue reporters (last 7 days)

| GitHub user | Issues opened |
|-------------|---------------|
| @user3 | 2 |
| @user4 | 1 |

### Links (sample)

**Discussions:**
- @user1: https://github.com/{owner}/{repo}/discussions/123
- @user2: https://github.com/{owner}/{repo}/discussions/456

**Issues:**
- @user3: https://github.com/{owner}/{repo}/issues/78
- @user4: https://github.com/{owner}/{repo}/issues/90

### Draft social post (edit before posting)

Huge thanks to the community members who contributed this week!

💬 Answered questions: @user1, @user2
🐛 Reported issues: @user3, @user4

Your help makes Learn to Cloud better for everyone. 🙌
```

If one section is empty (e.g. no discussion answers but some issues, or vice versa), omit that section but still create the issue.

## Important guidelines

- Do not include any private data (emails, IPs, etc.).
- GitHub usernames may not match social handles — this workflow only provides GitHub logins. Keep the post as "GitHub user" mentions unless you have verified handles separately.
- Keep the issue concise and optimized for copy/paste into a social media post.
