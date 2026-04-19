"""Deterministic indicator engine for PR diff grading.

Checks pass/fail indicators against a unified diff to produce a
deterministic pass/fail result.

Indicator matching rules:
- **fail_indicators**: ANY match in added/context lines → FAIL
- **pass_indicators**: AT LEAST ONE must match → PASS
  (indicators are alternatives, not cumulative requirements —
  e.g. ``import logging`` OR ``import structlog``)
- Matching is case-insensitive substring search
- Only non-removal lines are searched (added ``+`` and context lines)
- When ``expected_files`` is set, only diff hunks for those files are
  searched
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from schemas import HandsOnRequirement

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class IndicatorResult:
    """Result of deterministic indicator checking."""

    passed: bool
    matched_pass: list[str] = field(default_factory=list)
    missing_pass: list[str] = field(default_factory=list)
    matched_fail: list[str] = field(default_factory=list)
    reason: str = ""


# Regex to detect diff file headers: "diff --git a/path b/path" or
# "+++ b/path" lines.
_DIFF_FILE_HEADER = re.compile(r"^\+\+\+ b/(.+)$", re.MULTILINE)


def _extract_searchable_lines(
    diff: str,
    expected_files: list[str] | None,
) -> str:
    """Extract added/context lines from diff, optionally scoped to files.

    Args:
        diff: Full unified diff text (may include ``<pr_diff>`` wrapper).
        expected_files: If set, only include hunks from these file paths.

    Returns:
        Lowercased text of added and context lines for substring matching.
    """
    # Strip the safety wrapper if present
    diff = diff.replace("<pr_diff>", "").replace("</pr_diff>", "")

    if not expected_files:
        # No file scoping — search all non-removal lines
        lines = [line for line in diff.splitlines() if not line.startswith("-")]
        return "\n".join(lines).lower()

    # File-scoped: parse diff into per-file sections, keep only expected
    normalised_expected = {f.lower() for f in expected_files}
    sections = re.split(r"^diff --git ", diff, flags=re.MULTILINE)

    relevant_lines: list[str] = []
    for section in sections:
        # Find the target file path from "+++ b/..." header
        header_match = _DIFF_FILE_HEADER.search(section)
        if not header_match:
            continue
        file_path = header_match.group(1).lower()
        if file_path not in normalised_expected:
            continue
        # Collect non-removal lines from this section
        for line in section.splitlines():
            if not line.startswith("-"):
                relevant_lines.append(line)

    return "\n".join(relevant_lines).lower()


def check_indicators(
    diff: str,
    requirement: HandsOnRequirement,
) -> IndicatorResult:
    """Run deterministic indicator checks against a PR diff.

    Args:
        diff: Unified diff text (may include ``<pr_diff>`` wrapper).
        requirement: The requirement with indicators and expected_files.

    Returns:
        IndicatorResult with pass/fail and details on which indicators
        matched or were missing.
    """
    fail_indicators = requirement.fail_indicators or []
    pass_indicators = requirement.pass_indicators or []

    searchable = _extract_searchable_lines(diff, requirement.expected_files)

    # ── Check fail indicators first ──────────────────────────────
    matched_fail: list[str] = []
    for indicator in fail_indicators:
        if indicator.lower() in searchable:
            matched_fail.append(indicator)

    if matched_fail:
        logger.info(
            "indicator_engine.fail_indicators_found",
            extra={
                "requirement": requirement.id,
                "matched": matched_fail,
            },
        )
        return IndicatorResult(
            passed=False,
            matched_fail=matched_fail,
            reason=(
                "The PR diff still contains starter/placeholder code. "
                "Replace the stub implementation with your own code."
            ),
        )

    # ── Check pass indicators ────────────────────────────────────
    # Indicators are alternatives (e.g. "import logging" OR "import
    # structlog"), so at least one must match.
    matched_pass: list[str] = []
    missing_pass: list[str] = []
    for indicator in pass_indicators:
        if indicator.lower() in searchable:
            matched_pass.append(indicator)
        else:
            missing_pass.append(indicator)

    if not pass_indicators:
        # No indicators defined — cannot determine pass deterministically
        logger.warning(
            "indicator_engine.no_pass_indicators",
            extra={"requirement": requirement.id},
        )
        return IndicatorResult(
            passed=False,
            reason="No pass indicators defined for this requirement.",
        )

    if not matched_pass:
        logger.info(
            "indicator_engine.no_pass_indicators_matched",
            extra={
                "requirement": requirement.id,
                "missing": missing_pass,
            },
        )
        return IndicatorResult(
            passed=False,
            matched_pass=matched_pass,
            missing_pass=missing_pass,
            reason=(
                "The PR is missing required implementation. "
                "None of the expected code patterns were found."
            ),
        )

    # At least one pass indicator found, no fail indicators
    logger.info(
        "indicator_engine.all_indicators_passed",
        extra={
            "requirement": requirement.id,
            "matched": matched_pass,
        },
    )
    return IndicatorResult(
        passed=True,
        matched_pass=matched_pass,
        reason="All required indicators found in the PR diff.",
    )
