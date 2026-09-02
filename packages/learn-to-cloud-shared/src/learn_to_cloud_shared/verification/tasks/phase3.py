"""Phase 3 task definitions: final Journal API verification."""

from __future__ import annotations

from learn_to_cloud_shared.verification.tasks.base import (
    EvidencePolicy,
    LLMRubricGraderConfig,
    RubricCriterion,
    VerificationTask,
)

PHASE3_FINAL_REQUIREMENT_SLUG = "journal-api-implementation"

JOURNAL_API_IMPORTANT_PATHS = (
    "api/main.py",
    "api/routers/journal_router.py",
    "api/models/entry.py",
    "api/services/entry_service.py",
    "api/services/llm_service.py",
    ".devcontainer/devcontainer.json",
    "tests/test_journal_router.py",
    "tests/test_entry_service.py",
    "tests/test_llm_service.py",
    "tests/test_main.py",
    ".github/workflows/ci.yml",
    ".github/workflows/ci.yaml",
    "pyproject.toml",
    "requirements.txt",
)

JOURNAL_API_FINAL_RUBRIC_TASK = VerificationTask(
    id="journal-api-implementation-rubric",
    phase_id=3,
    requirement_slug=PHASE3_FINAL_REQUIREMENT_SLUG,
    name="Journal API Final Rubric Review",
    criteria=[
        RubricCriterion(
            id="application-logging",
            label="Application logging",
            instruction=(
                "Logging is configured in api/main.py without noisy or "
                "sensitive output."
            ),
        ),
        RubricCriterion(
            id="get-entry-endpoint",
            label="Get an entry",
            instruction=(
                "GET /entries/{entry_id} returns an entry and returns 404 when "
                "the entry is missing."
            ),
        ),
        RubricCriterion(
            id="delete-entry-endpoint",
            label="Delete an entry",
            instruction=(
                "DELETE /entries/{entry_id} deletes an entry and handles a "
                "missing entry with an appropriate 404 response."
            ),
        ),
        RubricCriterion(
            id="request-validation",
            label="Request validation",
            instruction=(
                "EntryCreate and EntryUpdate use explicit Pydantic validation."
            ),
        ),
        RubricCriterion(
            id="typed-patch-endpoint",
            label="Typed update endpoint",
            instruction=(
                "The PATCH endpoint uses EntryUpdate or an equivalent typed schema."
            ),
        ),
        RubricCriterion(
            id="journal-analysis",
            label="Journal analysis",
            instruction=(
                "analyze_journal_entry() calls the OpenAI SDK and returns "
                "entry_id, sentiment, summary, and topics."
            ),
        ),
        RubricCriterion(
            id="cloud-cli",
            label="Cloud CLI development tooling",
            instruction=(
                "The development environment enables at least one Azure, AWS, "
                "or GCP CLI feature."
            ),
        ),
        RubricCriterion(
            id="code-organization",
            label="Code organization",
            instruction=(
                "The code is readable, typed, and organized into clear modules."
            ),
        ),
        RubricCriterion(
            id="error-handling",
            label="Explicit error handling",
            instruction=(
                "Error handling is explicit and uses appropriate HTTP errors."
            ),
        ),
        RubricCriterion(
            id="credential-safety",
            label="Credential safety",
            instruction="No API keys, tokens, or credentials are hardcoded.",
        ),
        RubricCriterion(
            id="pythonic-clarity",
            label="Pythonic clarity",
            instruction=(
                "Prefer type hints and explicit dependencies over clever or "
                "implicit control flow."
            ),
            kind="quality",
        ),
        RubricCriterion(
            id="maintainability",
            label="Maintainability",
            instruction=(
                "Identify material maintainability risks even when CI is passing."
            ),
            kind="quality",
        ),
    ],
    grading_instructions=[
        "Grade only the supplied repository evidence and deterministic CI result.",
    ],
    evidence=EvidencePolicy(
        source="repo_files",
        path_patterns=[
            *JOURNAL_API_IMPORTANT_PATHS,
            "tests/",
            ".github/workflows/",
        ],
        max_files=12,
        max_file_size_bytes=35 * 1024,
        max_total_bytes=140 * 1024,
    ),
    grader=LLMRubricGraderConfig(
        rubric_id="phase3-journal-api-final-v2",
        prompt_version="2026-09-02",
        passing_score=0.8,
        model="gpt-5-mini",
    ),
)

PHASE3_LLM_TASKS = [JOURNAL_API_FINAL_RUBRIC_TASK]
