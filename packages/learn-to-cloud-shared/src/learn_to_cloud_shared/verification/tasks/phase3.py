"""Phase 3 task definitions: final Journal API verification."""

from __future__ import annotations

from learn_to_cloud_shared.verification.tasks.base import (
    EvidencePolicy,
    LLMRubricGraderConfig,
    VerificationTask,
)

PHASE3_FINAL_REQUIREMENT_ID = "journal-api-implementation"

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
    requirement_id=PHASE3_FINAL_REQUIREMENT_ID,
    name="Journal API Final Rubric Review",
    criteria=[
        "MUST grade only the supplied repository evidence and CI result",
        "MUST confirm logging is configured in api/main.py",
        "MUST confirm GET /entries/{entry_id} returns entries and 404s when missing",
        (
            "MUST confirm DELETE /entries/{entry_id} deletes entries and "
            "handles missing entries"
        ),
        "MUST confirm EntryCreate and EntryUpdate use explicit Pydantic validation",
        (
            "MUST confirm the PATCH endpoint uses the EntryUpdate model or "
            "equivalent typed schema"
        ),
        (
            "MUST confirm analyze_journal_entry() calls the OpenAI SDK and "
            "returns entry_id, sentiment, summary, and topics"
        ),
        (
            "MUST confirm at least one Azure, AWS, or GCP CLI devcontainer "
            "feature is enabled"
        ),
        "MUST confirm code is readable, typed, and organized into clear modules",
        "MUST confirm error handling is explicit and uses appropriate HTTP errors",
        "MUST confirm logging is configured without noisy or sensitive output",
        "MUST confirm no API keys, tokens, or credentials are hardcoded",
        (
            "SHOULD prefer Pythonic clarity, type hints, and explicit "
            "dependencies over clever or implicit control flow"
        ),
        "SHOULD identify maintainability risks even when CI is passing",
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
        rubric_id="phase3-journal-api-final-v1",
        prompt_version="2026-05-08",
        passing_score=0.8,
        model="gpt-5-mini",
    ),
)

PHASE3_LLM_TASKS = [JOURNAL_API_FINAL_RUBRIC_TASK]
