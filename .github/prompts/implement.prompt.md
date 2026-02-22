---
name: implement
description: Execute the approved plan fully — track progress, validate continuously, and don't stop until everything is done.
---
Implement it all. Follow the approved plan exactly — do not cherry-pick tasks or skip steps.

Find the plan document for the current topic (it will be named `{topic}-plan.md` in the repo root, e.g., `core-testing-plan.md`). If multiple plan files exist, ask which one to execute.

Rules:
- **Track progress**: When you finish a task or phase, mark it as completed in the plan document's todo list. The plan is the source of truth for progress.
- **Don't stop**: Do not pause for confirmation mid-flow. Do not stop until all tasks and phases are completed.
- **Validate continuously**: Run `ruff check`, `ruff format --check`, and `ty check` regularly as you go. Catch problems early, not at the end.
- **Keep code clean**: Do not add unnecessary comments or docstrings. Follow existing code style and patterns identified during research.
- **Strict typing**: Do not use `Any` or untyped escape hatches unless absolutely necessary.
- **Tests must be real**: Write clean, correct tests. If a test can't be written properly because the underlying code is wrong, document the issue in a separate `implementation-notes.md` and continue. Do not write tests that bandaid or cover up bad code.

By the time we're here, every decision has already been made in the plan. Implementation should be mechanical, not creative. Execute the plan.