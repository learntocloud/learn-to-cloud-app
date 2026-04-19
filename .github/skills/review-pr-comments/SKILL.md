---
name: review-pr-comments
description: This is used to review comments on an active pull request and decide whether to accept, iterate, or reject the changes suggested in each comment.
---
We have received comments on the current active pull request. Together, we will go through each comment one by one and discuss whether to accept the change, iterate on it, or reject the change.

## Steps to follow:

1. Fetch the active pull request: If available, use the `activePullRequest` tool from the `GitHub Pull Requests` toolset to get the details of the active pull request including the comments. If not, use the GitHub MCP server or GitHub CLI to get the details of the active pull request. Fetch both top level comments and inline comments.
2. Present a list of the comments with a one-sentence summary of each.
3. One at a time, present each comment in full detail and ask me whether to accept, iterate, or reject the change. Provide your recommendation for each comment based on best practices, code quality, and project guidelines. Await user's decision before proceeding to the next comment. DO NOT make any changes to the code or files until I have responded with my decision for each comment.
4. If the decision is to accept or iterate, make the necessary code changes to address the comment. If the decision is to reject, provide a brief explanation of why the change was not made.
5. Wait for user to affirm completion of any code changes made before moving to the next comment.
6. Reply to each comment on the pull request with the outcome of our discussion (accepted, iterated, or rejected) along with any relevant explanations.


## How to reply to PR review comments

This guide explains how to reply directly to inline review comments on GitHub pull requests.

### API Endpoint

To reply to an inline PR comment, use:

```http
POST /repos/{owner}/{repo}/pulls/{pull_number}/comments/{comment_id}/replies
```

With body:

```json
{
  "body": "Your reply message"
}
```

### Using gh CLI

```bash
gh api repos/{owner}/{repo}/pulls/{pull_number}/comments/{comment_id}/replies \
  -X POST \
  -f body="Your reply message"
```

### Workflow

1. **Get PR comments**: First fetch the PR review comments to get their IDs:

   ```bash
   gh api repos/{owner}/{repo}/pulls/{pull_number}/comments
   ```

2. **Identify comment IDs**: Each comment has an `id` field. For threaded comments, use the root comment's `id`.

3. **Post replies**: For each comment you want to reply to:

   ```bash
   gh api repos/{owner}/{repo}/pulls/{pull_number}/comments/{comment_id}/replies \
     -X POST \
     -f body="Fixed in commit abc123"
   ```

### Example Replies

For accepted changes:

- "Fixed in {commit_sha}"
- "Accepted - fixed in {commit_sha}"

For rejected changes:

- "Rejected - {reason}"
- "Won't fix - {explanation}"

For questions:

- "Good catch, addressed in {commit_sha}"

## Notes

- The `comment_id` is the numeric ID from the comment object, NOT the `node_id`
- Replies appear as threaded responses under the original comment
- You can reply to any comment, including bot comments (like Copilot reviews)

### Resolving Conversations

To resolve (mark as resolved) PR review threads, use the GraphQL API:

1. **Get thread IDs**: Query for unresolved threads:

   ```bash
   gh api graphql -f query='
   query {
     repository(owner: "{owner}", name: "{repo}") {
       pullRequest(number: {pull_number}) {
         reviewThreads(first: 50) {
           nodes {
             id
             isResolved
             comments(first: 1) {
               nodes { body path }
             }
           }
         }
       }
     }
   }'
   ```

2. **Resolve threads**: Use the `resolveReviewThread` mutation:

   ```bash
   gh api graphql -f query='
   mutation {
     resolveReviewThread(input: {threadId: "PRRT_xxx"}) {
       thread { isResolved }
     }
   }'
   ```

3. **Resolve multiple threads at once**:

   ```bash
   gh api graphql -f query='
   mutation {
     t1: resolveReviewThread(input: {threadId: "PRRT_xxx"}) { thread { isResolved } }
     t2: resolveReviewThread(input: {threadId: "PRRT_yyy"}) { thread { isResolved } }
   }'
   ```

The thread ID starts with `PRRT_` and can be found in the GraphQL query response.

Note: This skill can be removed once the GitHub MCP server has added built-in support for replying to PR review comments and resolving threads.
See:
https://github.com/github/github-mcp-server/issues/1323
https://github.com/github/github-mcp-server/issues/1768
