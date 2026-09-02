"""Phase 6 task definitions: security scanning verification.

The deterministic gate (``codeql_status``) proves CodeQL ran green on the
current ``main`` HEAD. The LLM rubric below does *not* re-check that a scan
ran; it grades the committed workflow's **quality** and confirms it targets
**Python**, so it stays non-redundant with the gate.
"""

from __future__ import annotations

from learn_to_cloud_shared.verification.tasks.base import (
    EvidencePolicy,
    LLMRubricGraderConfig,
    RubricCriterion,
    VerificationTask,
)

PHASE6_REQUIREMENT_SLUG = "security-scanning"
CODEQL_WORKFLOW_PATH = ".github/workflows/codeql.yml"
DEPENDABOT_CONFIG_PATHS = (".github/dependabot.yml", ".github/dependabot.yaml")

SECURITY_SCANNING_RUBRIC_TASK = VerificationTask(
    id="security-scanning-rubric",
    phase_id=6,
    requirement_slug=PHASE6_REQUIREMENT_SLUG,
    name="Security Scanning Rubric Review",
    criteria=[
        RubricCriterion(
            id="python-analysis",
            label="Python analysis",
            instruction=(
                "The CodeQL workflow includes Python in its languages or "
                "build-mode configuration."
            ),
        ),
        RubricCriterion(
            id="workflow-triggers",
            label="Security scan triggers",
            instruction=(
                "The workflow runs on push and pull requests to the default "
                "branch and on a schedule."
            ),
            kind="quality",
        ),
        RubricCriterion(
            id="query-suite",
            label="Deliberate query suite",
            instruction=(
                "The workflow selects a deliberate query suite such as "
                "security-extended rather than relying only on defaults."
            ),
            kind="quality",
        ),
        RubricCriterion(
            id="pinned-actions",
            label="Pinned CodeQL actions",
            instruction=("github/codeql-action steps are pinned to a tag or SHA."),
            kind="quality",
        ),
        RubricCriterion(
            id="dependabot",
            label="Dependabot updates",
            instruction=(
                "Dependabot has a version key and at least one updates entry."
            ),
            kind="bonus",
        ),
    ],
    grading_instructions=[
        "Grade only the repository evidence provided.",
        (
            "Do not re-grade whether a scan ran or passed because a separate "
            "deterministic gate proves that."
        ),
    ],
    evidence=EvidencePolicy(
        source="repo_files",
        path_patterns=[CODEQL_WORKFLOW_PATH, *DEPENDABOT_CONFIG_PATHS],
        max_files=3,
        max_total_bytes=75 * 1024,
    ),
    grader=LLMRubricGraderConfig(
        rubric_id="phase6-security-scanning-v3",
        prompt_version="2026-09-02",
        passing_score=0.75,
        model="gpt-5-mini",
    ),
)

PHASE6_LLM_TASKS = [SECURITY_SCANNING_RUBRIC_TASK]
