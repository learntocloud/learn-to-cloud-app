---
name: review-pr-comments
description: Triage and address top-level and inline comments on the active pull request. Use for "review PR comments", "address review comments", or "handle PR feedback".
---

# Review Pull Request Comments

Use `gh` to identify the pull request for the current branch and fetch issue
comments, reviews, inline comments, and unresolved review threads.

1. Present each actionable comment once with its author, location, summary, and
   recommendation: accept, iterate, reject, or answer only.
2. Ask for the user's decision one comment at a time. Do not edit before that
   comment's decision.
3. For accepted or iterated feedback, make and validate the change. For rejected
   feedback, record the technical reason.
4. Reply directly to the originating comment with the outcome and commit SHA
   when available. Resolve an inline thread only after its outcome is delivered.

Ignore superseded comments and bot summaries that contain no actionable
feedback. Never claim a comment is addressed before the change is present and
validated.
