-- migration_data_shapes.sql
--
-- Append-only fixture of "weird shapes seen in prod." Each time a
-- migration failure surfaces a new data pattern, the fix PR adds
-- INSERTs here so the migration-chain test catches regressions.
--
-- The test stamps the database at revision 0019, loads this file,
-- then runs ``alembic upgrade head``.  Data must be valid at the
-- 0019 schema (all NOT NULL / CHECK constraints enforced by 0019).
--
-- IMPORTANT: only append to this file. Never edit or remove rows.

-- ============================================================
-- Users
-- ============================================================
INSERT INTO users (id, github_username, is_admin, created_at, updated_at)
VALUES
  (1001, 'alice',   false, NOW(), NOW()),
  (1002, 'bob',     false, NOW(), NOW()),
  (1003, 'charlie', true,  NOW(), NOW());

-- ============================================================
-- Submissions (various types and states)
-- ============================================================
INSERT INTO submissions
  (user_id, requirement_id, submission_type, phase_id,
   submitted_value, is_validated, verification_completed,
   created_at, updated_at)
VALUES
  -- Validated submission
  (1001, 'phase1-github-profile', 'github_profile', 1,
   'https://github.com/alice', true, true, NOW(), NOW()),
  -- Unvalidated submission
  (1002, 'phase1-github-profile', 'github_profile', 1,
   'https://github.com/bob', false, false, NOW(), NOW()),
  -- CTF token submission
  (1001, 'phase2-networking', 'networking_token', 2,
   'flag{test123}', true, true, NOW(), NOW());

-- ============================================================
-- Step progress
-- ============================================================
INSERT INTO step_progress
  (user_id, topic_id, phase_id, step_order, step_id, completed_at)
VALUES
  (1001, 'linux-basics', 1, 1, 'linux-basics-step-1', NOW()),
  (1001, 'linux-basics', 1, 2, 'linux-basics-step-2', NOW()),
  (1002, 'linux-basics', 1, 1, 'linux-basics-step-1', NOW());

-- ============================================================
-- Verification jobs: the #432 incident pattern
--
-- Ghost rows: terminal status but result_submission_id IS NULL.
-- Two such rows for the SAME (user_id, requirement_id) pair.
-- Before the fix in 0020, these would violate the new partial
-- unique index on (user_id, requirement_id) WHERE
-- result_submission_id IS NULL.
-- ============================================================
INSERT INTO verification_jobs
  (id, user_id, requirement_id, phase_id, submission_type,
   submitted_value, status, result_submission_id,
   created_at, updated_at)
VALUES
  -- Ghost row 1: failed, no linked submission
  ('a0000000-0000-0000-0000-000000000001',
   1001, 'phase1-github-profile', 1, 'github_profile',
   'https://github.com/alice', 'failed', NULL,
   NOW(), NOW()),
  -- Ghost row 2: same user+requirement, also failed, no linked submission
  -- This is the duplicate that caused incident #432
  ('a0000000-0000-0000-0000-000000000002',
   1001, 'phase1-github-profile', 1, 'github_profile',
   'https://github.com/alice', 'server_error', NULL,
   NOW(), NOW()),
  -- Normal completed job with a linked submission (not a ghost)
  ('a0000000-0000-0000-0000-000000000003',
   1001, 'phase2-networking', 2, 'networking_token',
   'flag{test123}', 'succeeded', 3,
   NOW(), NOW()),
  -- Active job (queued, no result yet) -- should survive cleanup
  ('a0000000-0000-0000-0000-000000000004',
   1002, 'phase1-github-profile', 1, 'github_profile',
   'https://github.com/bob', 'queued', NULL,
   NOW(), NOW());
