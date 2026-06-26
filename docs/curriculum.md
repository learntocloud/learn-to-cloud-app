# Curriculum Domain Model

This doc explains the architecture that powers Learn to Cloud's curriculum:
phases, topics, learning steps, learning objectives, and hands-on
verification requirements. If you're editing curriculum content or
touching code that reads or writes user progress, start here.

Context: this design landed across issues #461 through #466 (and the
sub-issues #462 to #470). The high-level shape is YAML-authoritative
content + deploy-time sync to Postgres + UUID FKs for user state.

## The model

```
Phase ── Topic ── LearningStep
       │       └─ LearningObjective
       └─ HandsOnRequirement (per phase, hands-on verifications)
```

Each entity has two ids:

- `uuid` — Postgres primary key. Used for foreign keys and as the stable
  identity that survives YAML edits.
- `slug` — the human-readable id from YAML. For phases that's
  `"phase0"`..`"phase7"` (with an integer `order` 0..7 for URLs); for
  topics/steps/objectives/requirements it's the kebab-case slug
  (`prepare-to-learn`, `phase0-topic0-watch-...`, `github-profile`).
  Used in URLs, templates, seed scripts, and log lines so humans can
  read what's going on without joining against the curriculum table.

Both fields are stored on every curriculum row. Loaders that hand a
`HandsOnRequirement` (or any other Pydantic schema) to the rest of
the app surface `slug` for templates and `uuid` for repository writes.

## The flow

```
YAML files  ──(deploy-time sync)──>  Postgres curriculum tables  ──>  app reads
   ▲                                          ▲
   │                                          │
 authored                                user state
 by editors                            (step_progress,
                                       submissions,
                                       verification_jobs)
                                       references via UUID FK
```

### YAML is authoritative

Curriculum lives under
`packages/learn-to-cloud-shared/src/learn_to_cloud_shared/content/phases/`.
Each phase has a directory:

```
phase0/
  _phase.yaml                  # phase metadata + topic/requirement slug lists
  intro-to-the-cloud.yaml      # one file per topic, slug = filename stem
  ...
  requirements/
    github-profile.yaml        # one file per hands-on requirement
    ...
```

The `_phase.yaml` file owns the order of its topics and requirements via
slug lists. Topic and requirement files must not carry an `order`
field; loaders reject it (one source of truth, per #463).

Editing curriculum is a normal YAML PR: change the files, push, let CI
validate. The deploy then syncs your changes into Postgres.

### Sync happens at deploy time

The migrations job (Azure Container Apps Manual Job) runs
`api/scripts/run_migrations.py` which:

1. Runs `alembic upgrade head`.
2. Runs `alembic current --check-heads` to fail loud if HEAD slipped.
3. Runs `alembic check` to fail if the ORM disagrees with the DDL.
4. Runs `python -m learn_to_cloud_shared.cli.sync_curriculum` against the
   target database.

The sync (`learn_to_cloud_shared.content_sync.sync_curriculum_to_db`):

- Loads YAML via `content_yaml_loader.get_all_phases_from_yaml`.
- Runs strict cross-file validators (`content_yaml_loader.validate_content`):
  global UUID uniqueness, topic slug resolution, step order uniqueness,
  requirement slug resolution, requirement id uniqueness.
- Upserts each curriculum row by UUID.
- Soft-deletes any active row whose UUID is no longer in the YAML
  (`deleted_at` column, not a `DELETE`). This protects user state FKs.
- Refuses to run if YAML loaded zero phases unless
  `allow_empty=True` — a defense against accidentally wiping the
  curriculum tables.

### Runtime reads from Postgres

Public entry point: `learn_to_cloud_shared.content_service`. The four
functions return Pydantic shapes built from the DB tables:

```python
async def get_all_phases(db) -> tuple[Phase, ...]
async def get_phase_by_slug(db, slug) -> Phase | None
async def get_topic_by_uuid(db, topic_uuid) -> Topic | None
async def get_topic_by_slugs(db, phase_slug, topic_slug) -> Topic | None
```

`content_db_loader` does the actual work: 5 simple `SELECT ... WHERE
deleted_at IS NULL ORDER BY order` queries (one per table) and
in-Python grouping by parent UUID. Uncached by design — the
curriculum is small (~466 active rows) and a process-level cache
without invalidation creates a class of stale-data bugs we wanted
to avoid (PR #476 / #474 discussion).

The YAML loader (`content_yaml_loader`) is only imported from
`content_sync` and `scripts/validate_content.py`. It must not be
imported from request-serving code.

### User state references curriculum via UUID FKs

After Phase D (#465):

| Table | FK to | Constraint |
|---|---|---|
| `step_progress.step_uuid` | `steps.uuid` | `ON DELETE RESTRICT` |
| `submissions.requirement_uuid` | `requirements.uuid` | `ON DELETE RESTRICT` |
| `verification_jobs.requirement_uuid` | `requirements.uuid` | `ON DELETE RESTRICT` |

`ON DELETE RESTRICT` means curriculum rows can never be hard-deleted
while user state references them. Soft-delete (`deleted_at` set) is
the only delete mechanism the sync uses; the FK still resolves so
historical submissions remain valid.

`requirements.slug` (the kebab-case human id) carries a partial
unique index across active rows + a globally unique index ignoring
`deleted_at`. The latter exists because the slug appears in URLs,
templates, and log lines as the public id; duplicates across phases
would break that contract.

Repository APIs take and return UUIDs. The service layer translates
to/from slugs at the boundary when templates or HTMX form payloads
need them.

## Editing curriculum

### Add a new step to a topic

1. Edit the topic YAML file under
   `content/phases/phase<N>/<topic-slug>.yaml`. Add the step to
   `learning_steps` with a new `id`, `uuid` (generate a new one),
   `title`, etc.
2. (Optional but recommended) Run
   `cd packages/learn-to-cloud-shared && uv run python scripts/validate_content.py`
   locally.
3. Open a PR. CI runs validators + the API test suite.
4. After merge, the deploy job syncs your YAML into Postgres. No
   migration needed for curriculum content changes.

### Add a new hands-on requirement

1. Create `content/phases/phase<N>/requirements/<slug>.yaml` with the
   discriminated `type_config` for your submission type (see
   `learn_to_cloud_shared.schemas.HandsOnRequirement`).
2. Add the slug to the parent phase's `_phase.yaml`
   `hands_on_verification.requirements:` list (position = display
   order).
3. Generate a UUID for the `uuid` field. Set `id` = filename stem.
4. The requirement id must be globally unique across all phases —
   it's used as a public submission key.
5. Open a PR; CI validates; deploy syncs.

### Soft-delete a requirement

Remove the slug from `_phase.yaml`'s `requirements:` list and remove
the per-requirement file. The sync sets `deleted_at` on the
existing row. User state for the removed requirement stays intact
(FK ON DELETE RESTRICT). The active read path
(`get_all_phases`) filters out soft-deleted rows so the requirement
disappears from the app, but historical submissions still resolve
their `requirement_uuid` for display and accounting.

## Adding a schema change to curriculum tables

Phase B (#463) created the curriculum tables. Schema changes follow
the normal Alembic flow described in
[`docs/migrations.md`](./migrations.md). A few patterns specific to
these tables:

- The sync upserts by UUID, so adding a new column with a default is
  trivially safe — the next deploy populates it for every row.
- Adding a required column needs the standard "ADD nullable + backfill
  + SET NOT NULL via CHECK-then-flip" pattern documented in
  `docs/migrations.md`.
- Soft-deletes use partial unique indexes (`postgresql_where=
  text("deleted_at IS NULL")`) so collisions on active rows fail loud
  while keeping the soft-deleted history intact.

## Why this shape

A few decisions worth knowing if you find yourself second-guessing
them later:

- **YAML over admin UI**: this is a learning curriculum maintained by
  a small group of editors via PRs. A UI would be more work than the
  audience justifies, and PR review on YAML diffs is genuinely useful.
- **UUID PKs from day one**: lets us reorder, rename, or copy
  curriculum content without breaking user state.
- **`slug` on every row**: humans look at URLs, templates, and
  log lines. Forcing them to look up a UUID just to discuss "step 3
  of topic 1" would be needlessly hostile. Carry the slug too.
- **Per-request DB reads, no cache**: the curriculum is small enough
  (~10 queries that hit indexes) that a request-scoped cache wouldn't
  pay for itself. A process-level cache requires invalidation and the
  sync needs to know about it.
- **Sync over migrations for content**: schema changes go through
  Alembic; content changes go through the sync. Mixing them would
  make migrations harder to review and content changes harder to roll
  back.
