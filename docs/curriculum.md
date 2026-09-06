# Curriculum Architecture

Curriculum content is authored as YAML, compiled into a deterministic JSON
artifact, and loaded into an indexed in-memory catalog by each application
process. PostgreSQL stores learner state only; it does not store curriculum
content.

## Content flow

```text
YAML files -> strict validation -> curriculum.json -> in-memory catalog
```

Authored YAML lives under
`packages/learn-to-cloud-shared/src/learn_to_cloud_shared/content/phases/`.
Each phase directory contains `_phase.yaml`, topic files, and requirement files.
The phase file owns topic and requirement order.

`scripts/compile_curriculum.py` validates the complete tree and writes the
packaged `content/curriculum.json` artifact. CI rejects a branch when generated
artifact content differs from the committed artifact.

At runtime, `content_catalog.py` loads the artifact once and builds dictionaries
for UUID, slug, phase, topic, step, and requirement lookup.
`content_service.py` is the public read API.

## Learner state

PostgreSQL stores only durable learner state:

| Table | Purpose |
|---|---|
| `users` | GitHub-authenticated learner accounts |
| `auth_sessions` | Revocable login-session digests, account ownership, and expiry timestamps |
| `learner_step_completions` | Checked learning steps, keyed by catalog UUID |
| `verification_attempts` | Submitted verification attempts and outcomes |

Step and requirement UUIDs intentionally have no foreign keys to curriculum
tables. Current progress intersects stored UUIDs with the active catalog, so
retired content stops counting without deleting learner history.

## Repository-based verification

One shared ownership check runs before profile README (Phase 0), repository
forks (Phases 1/2), Journal API (Phase 3), deployment architecture (Phase 4),
DevOps (Phase 5), and security scanning (Phase 6) checks. The public repository
must belong to the signed-in learner's numeric GitHub ID. Existing fork, CI,
file, deployment-description, GHCR, CodeQL, and rubric requirements still apply.

Verification uses the saved GitHub username. If a username change causes an
ownership or repository-not-found failure, sign out, sign in again, and submit
a new attempt. GitHub service failures leave verification incomplete.
Token-only, deployed-API URL, and career-reflection checks do not perform this
repository lookup. Existing completions and stored submission links are not
rewritten.

## Editing curriculum

1. Edit the YAML files.
2. Run `cd packages/learn-to-cloud-shared && uv run poe check`.
3. Commit both the YAML changes and regenerated `curriculum.json`.

Adding or removing curriculum content does not require a database migration.
