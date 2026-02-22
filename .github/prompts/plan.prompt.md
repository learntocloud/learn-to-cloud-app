---
name: plan
description: Create a detailed, annotatable implementation plan based on completed research. No code gets written until the plan is approved.
---
Using the research you've done, write a detailed plan document outlining how to implement this. Read the actual source files before suggesting changes — base the plan on the real codebase, not assumptions.

## Output File

Name the plan file based on the topic being planned:
- Use the pattern `{topic}-plan.md` in the repo root (e.g., `core-testing-plan.md`, `caching-strategy-plan.md`)
- **Never overwrite `plan.md`** — that file may contain a prior plan on a different topic
- If the user doesn't specify a topic name, derive a short kebab-case slug from their request

The plan must include:
- **Approach**: A clear explanation of the strategy and why this approach was chosen
- **File paths**: Every file that will be created, modified, or deleted
- **Code snippets**: Show the actual changes — not pseudocode, real code based on our existing patterns
- **Trade-offs**: What alternatives were considered and why they were rejected
- **Risks & edge cases**: What could go wrong and how we handle it
- **API verification**: When the plan includes code snippets that use external libraries, use context7 to verify the APIs exist in the current version. Do not propose code that uses deprecated or non-existent methods.
- **Todo list**: A granular, checkable task breakdown with all phases and individual tasks needed to complete the plan

I will review this plan in my editor and add inline notes to correct assumptions, reject approaches, or add constraints. When I send you back to the document, address all my notes and update the plan accordingly.

**Do not implement yet.** Do not write any code until I explicitly approve the plan. The plan is not good enough until I say it is.
