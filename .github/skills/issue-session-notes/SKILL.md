---
name: issue-session-notes
description: Attach relevant Copilot session lessons, mistakes, decisions, model details, token usage, MCP servers, and skills to a GitHub issue comment. Use when the user asks to add session notes, lessons learned, Copilot notes, mistakes, or implementation details to an issue.
---

# Attach Copilot Session Notes to a GitHub Issue

Use this skill to create or update a GitHub issue comment with the useful parts of a
Copilot session. The goal is to leave behind context that helps the next person
continue the issue without reading the full chat transcript.

Prefer one living comment per issue. Update that comment instead of creating many
new comments, because GitHub issue comments notify subscribers and rapid comment
creation can hit secondary rate limits.

## When to Use

- User asks to attach Copilot session notes to an issue
- User asks for lessons learned, mistakes, discoveries, or implementation details
- User asks to document what happened while working on an issue
- User asks to include model, token usage, MCP servers, or skills used

## Do Not Include

- Secrets, credentials, tokens, private URLs, or sensitive logs
- Full raw conversation transcripts
- Large command output unless a short excerpt is needed to explain a failure
- Unrelated exploration
- Speculation that was not verified

## Inputs to Gather

Gather only what is available. If a field is unavailable, write `Not available`
rather than guessing.

1. Issue number or URL.
2. Repository, if not the current repository.
3. Related branch, pull request, or commit, if available.
4. Session date.
5. Model used.
6. Token usage.
7. MCP servers or tool servers actually used.
8. Skills actually used.
9. Relevant lessons, mistakes, decisions, blockers, and next actions.

Useful Copilot CLI commands from the help menu:

- `/usage` for session usage metrics and token information
- `/env` for loaded MCP servers, skills, agents, plugins, and instructions
- `/search` to find important moments in the conversation timeline
- `/diff` to review code changes before summarizing them
- `/tasks` to review subagents and shell commands used during the session
- `/share` only when a longer, scrubbed artifact is worth linking

If slash command output is not directly available to the agent, summarize from the
visible conversation and tool history, and mark unknown fields as `Not available`.

## Comment Format

Use this markdown template. Keep the note short and concrete.

```md
<!-- copilot-session-notes:v1 issue=<issue-number> -->

## Copilot session notes

**Session date:** <YYYY-MM-DD>
**Related work:** <branch, PR, commit, or Not available>
**Model used:** <model name and model ID, or Not available>
**Token usage:** <input/output/total if available, or Not available>
**MCP/tool servers used:** <comma-separated list, or None observed>
**Skills used:** <comma-separated list, or None observed>
**Available but not used:** <optional short list, or omit>

### What we learned

- <Relevant discovery or lesson. Explain why it matters for this issue.>

### Mistakes or false starts

- <What was tried, what went wrong, and how to avoid repeating it.>

### Important implementation details

- <Decision, constraint, edge case, file, command, or validation detail.>

### Next action

- <One concrete next step, or "None.">
```

## What Counts as Relevant

Include information that would help someone continue the issue later:

| Include | Skip |
| --- | --- |
| Root cause of a bug | Full raw chat transcript |
| Failed approach and why it failed | Routine command output |
| Important repo convention discovered | Token values, secrets, or credentials |
| Validation commands that matter | Every command that happened to run |
| Files, functions, or workflows involved | Unrelated exploration |
| Tradeoff or decision made | Vague notes like "Copilot fixed it" |
| Open question or blocker | Unverified guesses |

## Posting the Comment

Prefer GitHub CLI for issue comments:

```bash
gh issue comment <issue-number-or-url> \
  --body-file <notes-file> \
  --edit-last \
  --create-if-none
```

Use standard issue comments for general session notes. For pull request timeline
comments, use:

```bash
gh pr comment <pr-number-or-url> \
  --body-file <notes-file> \
  --edit-last \
  --create-if-none
```

Only use pull request review comments when the note belongs on a specific changed
line.

## API Fallback

If GitHub CLI cannot be used, create an issue comment with the REST API:

```http
POST /repos/{owner}/{repo}/issues/{issue_number}/comments
```

Request body:

```json
{
  "body": "comment markdown"
}
```

Use `Accept: application/vnd.github+json` when making API requests.

## Quality Rules

- Keep the comment readable for non-engineers.
- Prefer short bullets with plain language.
- Make unknown metadata explicit with `Not available`.
- Do not invent token usage, model names, MCP servers, or skills.
- Separate tools actually used from tools that were only available.
- Update the existing notes comment when possible.
- End with a next action so the issue remains actionable.
