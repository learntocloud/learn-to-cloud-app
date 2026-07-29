# Dog Food QA Reference

Read only the section you need. The page tables are a **coverage backstop**, not
a checklist: pursue the user's goal first, then use these to make sure a run
touched the main surface. "Expected evidence" is the minimum that proves a page
rendered, not the full definition of working.

## Public pages

| Page | URL |
|------|-----|
| Home | `http://localhost:8000/` |
| Curriculum | `http://localhost:8000/curriculum` |
| FAQ | `http://localhost:8000/faq` |
| Privacy | `http://localhost:8000/privacy` |
| Terms | `http://localhost:8000/terms` |

## Authenticated pages

| Page | URL | Expected evidence |
|------|-----|-------------------|
| Dashboard | `/dashboard` | Navigation, main content, username |
| Account | `/account` | Navigation, main content, account settings |
| Phase 0 | `/phase/0` | Navigation, main content, no server error |
| Phase 1 | `/phase/1` | Navigation, main content, topic links |
| Phase 2 | `/phase/2` | Navigation, main content, no server error |
| Phase 3 | `/phase/3` | Navigation, main content, no server error |
| Phase 4 | `/phase/4` | Navigation, main content, no server error |
| Phase 5 | `/phase/5` | Navigation, main content, no server error |
| Phase 6 | `/phase/6` | Navigation, main content, no server error |
| Phase 7 | `/phase/7` | Navigation, main content, no server error |
| First topic | First `/phase/1/*` link | Learning steps and checkboxes |

## Submission requirements

| Phase | Requirement slug | Submission type | Needs Functions? | Input |
|-------|------------------|-----------------|------------------|-------|
| 1 | `profile-readme` | `profile_readme` | Yes | Auto-derived |
| 1 | `linux-ctfs-fork` | `repo_fork` | Yes | Auto-derived |
| 1 | `linux-ctfs-token` | `ctf_token` | Yes | User-provided token |
| 2 | `networking-lab-fork` | `repo_fork` | Yes | Auto-derived |
| 2 | `networking-lab-token` | `networking_token` | Yes | User-provided token |
| 3 | `journal-api-implementation` | `journal_api_verifier` | Yes | Auto-derived |
| 4 | `deployed-journal-api` | `deployed_api` | Yes | User-provided URL |
| 5 | `devops-implementation` | `devops_analysis` | Yes | Auto-derived |
| 6 | `security-scanning` | `security_scanning` | Yes | Auto-derived |
| 7 | `career-reflection` | `career_reflection` | Yes | Three user-provided answers |

Auto-derived values come from the authenticated GitHub user. For
`career_reflection`, fill every rendered textarea with a substantive answer of
at least 200 characters.

## Report template

Lead with findings. The tables exist so the reader knows what was covered; they
are not the point of the report.

````markdown
## Dog Food Report

**Goal:** what you set out to do
**Verdict:** one sentence — did the goal succeed, partially succeed, or fail

### Defects

Objective breakage. For each: what you did, what you saw, the server-side
evidence (exception type and application frame), and how to reproduce.

1. ...

### Friction

Things that worked but shouldn't ship as-is: dead-looking controls, messages
that don't say what to do next, flows that made you guess.

1. ...

### Coverage

| Area | Exercised | Result |
|------|-----------|--------|
| Public pages | which ones | clean / see defect N |
| Authenticated pages | which ones | clean / see defect N |
| Interactions | dark mode, step toggle, ... | clean / see defect N |
| Submission | phase + requirement | passed / failed / timed out |

**Not exercised:** everything you did not reach, and why.

### Environment

| Item | Value |
|------|-------|
| API | healthy / failed, PID |
| Functions | healthy / not needed / failed, PID |
| Processes stopped | Yes/No |
| Logs | `/tmp/dogfood-api.log`, `/tmp/dogfood-functions.log` |
````

This report is evidence of what was found, not proof the app is healthy.
