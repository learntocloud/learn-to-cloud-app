---
name: research
description: Deep-read the relevant codebase and external sources before any planning or implementation.
---
Read the relevant parts of the codebase **deeply** — not just function signatures, but the actual logic, existing patterns, caching layers, ORM conventions, and how data flows end-to-end. Understand the intricacies. Surface-level reading is not acceptable.

Also use web research, official docs, and library source code where needed to understand best practices for any new tools or patterns we'd adopt.

## Output File

Name the research file based on the topic being researched:
- Use the pattern `{topic}-research.md` in the repo root (e.g., `azure-mcp-vs-cli-research.md`, `caching-strategy-research.md`)
- **Never overwrite `research.md`** — that file may contain prior research on a different topic
- If the user doesn't specify a topic name, derive a short kebab-case slug from their request

## Required Sections

The research document must include:
- How the relevant system currently works (with file paths and code references)
- Existing patterns and conventions we must follow
- Links to external resources, docs, or reference implementations
- Code snippets showing current behavior and proposed approaches
- Potential gotchas — things that could break if we're not careful (e.g., duplicating logic that already exists, ignoring existing abstractions)

This document is my review surface. I will read it to verify you actually understood the system before any planning happens. If the research is wrong, the plan will be wrong. Do not plan or implement anything yet.
