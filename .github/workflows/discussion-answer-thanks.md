---
description: |
  Weekly rollup of community members who reported issues,
  for a weekly social media thank-you post.

on:
  schedule: weekly on sunday
  workflow_dispatch:

permissions:
  contents: read
  issues: read

network: defaults

tools:
  github:
    lockdown: false

safe-outputs:
  create-issue:
    title-prefix: "[community-thanks] "
    labels: [community, automation]
    close-older-issues: true
---

# Weekly Community Thanks

Create a weekly rollup of people who reported issues in this repository, so we can thank them in a social media post.

## What to include

- Users who opened issues (not PRs) in the last 7 days
- A draft social media post listing everyone, ready to copy/paste

Exclude bots (logins ending in `[bot]`).

## Process

1. Use the GitHub tools to list issues opened in the last 7 days. Filter out pull requests and bots.

2. Aggregate by GitHub username: count issues, collect sample links.

3. If no issues were opened, use the noop output.

4. Otherwise, create an issue with a summary table and a draft social post:

```markdown
## Community Thanks — {date}

### 🐛 Issue reporters (last 7 days)

| GitHub user | Issues opened |
|-------------|---------------|
| @user1 | 2 |
| @user2 | 1 |

### Draft social post

Huge thanks to the community members who reported issues this week!
🐛 @user1, @user2
Your feedback makes Learn to Cloud better for everyone. 🙌
```

Keep it concise for easy copy/paste.
