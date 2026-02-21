---
description: |
  Weekly rollup of community members who answered questions in GitHub Discussions
  or reported issues, for a weekly social media thank-you post.

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
  bash: ["date", "gh"]

safe-outputs:
  create-issue:
    title-prefix: "[community-thanks] "
    labels: [community, automation]
    close-older-issues: true
---

# Weekly Community Thanks

Create a weekly rollup of people who answered questions in GitHub Discussions or reported issues, so we can thank them in a social media post.

## What to include

- **Discussion helpers**: users who commented on or answered Q&A discussions in the last 7 days
- **Issue reporters**: users who opened issues (not PRs) in the last 7 days
- A draft social media post listing everyone, ready to copy/paste

Exclude bots (logins ending in `[bot]`).

## Process

1. Use `gh api graphql` to fetch recent discussions with comments and answers:
   ```bash
   gh api graphql -f query='query($owner:String!,$repo:String!){
     repository(owner:$owner,name:$repo){
       discussions(first:50, orderBy:{field:UPDATED_AT, direction:DESC}){
         nodes{ number title url updatedAt
           comments(first:50){ nodes{ createdAt author{ login } } }
           answer{ createdAt author{ login } }
         }
       }
     }
   }' -f owner='${{ github.repository_owner }}' -f repo='$(echo "${{ github.repository }}" | cut -d/ -f2)'
   ```

2. Use the GitHub tools to list issues opened in the last 7 days. Filter out pull requests and bots.

3. Aggregate by GitHub username: count answers, count issues, collect sample links.

4. If no contributions found, use the noop output.

5. Otherwise, create an issue with a summary table and a draft social post:

```markdown
## Community Thanks — {date}

### 💬 Discussion helpers (last 7 days)

| GitHub user | Answers | Discussions helped |
|-------------|---------|---------------------|
| @user1 | 5 | 3 |

### 🐛 Issue reporters (last 7 days)

| GitHub user | Issues opened |
|-------------|---------------|
| @user2 | 2 |

### Draft social post

Huge thanks to the community members who contributed this week!
💬 Answered questions: @user1
🐛 Reported issues: @user2
Your help makes Learn to Cloud better for everyone. 🙌
```

Omit empty sections. Keep it concise for easy copy/paste.
