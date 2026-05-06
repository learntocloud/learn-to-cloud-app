"""Tests for the deterministic indicator engine.

Tests cover:
- All pass indicators present → pass
- Missing pass indicators → fail with specifics
- Fail indicators found → fail
- File scoping (expected_files)
- Added-lines-only matching (not removed lines)
- No indicators defined → fail
"""

import pytest

from learn_to_cloud_shared.models import SubmissionType
from learn_to_cloud_shared.schemas import HandsOnRequirement
from learn_to_cloud_shared.verification.indicator_engine import check_indicators


def _make_requirement(
    pass_indicators: list[str] | None = None,
    fail_indicators: list[str] | None = None,
    expected_files: list[str] | None = None,
) -> HandsOnRequirement:
    return HandsOnRequirement(
        id="test-req",
        submission_type=SubmissionType.PR_REVIEW,
        name="Test Requirement",
        description="Test",
        pass_indicators=pass_indicators,
        fail_indicators=fail_indicators,
        expected_files=expected_files,
    )


# A realistic diff with added lines
_PASSING_DIFF = """\
<pr_diff>
diff --git a/api/main.py b/api/main.py
--- a/api/main.py
+++ b/api/main.py
@@ -1,3 +1,8 @@
+import logging
+
+logging.basicConfig(level=logging.INFO)
+logger = logging.getLogger(__name__)
+logger.info("App starting")
 from fastapi import FastAPI
 app = FastAPI()
</pr_diff>"""

_FAILING_DIFF_WITH_STUB = """\
<pr_diff>
diff --git a/api/main.py b/api/main.py
--- a/api/main.py
+++ b/api/main.py
@@ -1,3 +1,5 @@
+# TODO (Task 1): Configure logging here.
+import logging
 from fastapi import FastAPI
 app = FastAPI()
</pr_diff>"""

_DIFF_WITH_REMOVED_LINES = """\
<pr_diff>
diff --git a/api/main.py b/api/main.py
--- a/api/main.py
+++ b/api/main.py
@@ -1,5 +1,3 @@
-import logging
-logging.basicConfig(level=logging.INFO)
+import structlog
+structlog.configure()
 from fastapi import FastAPI
</pr_diff>"""

_MULTI_FILE_DIFF = """\
<pr_diff>
diff --git a/api/routers/journal_router.py b/api/routers/journal_router.py
--- a/api/routers/journal_router.py
+++ b/api/routers/journal_router.py
@@ -10,3 +10,6 @@
+entry_service.get_entry
+status_code=404
 @app.get("/entries")
diff --git a/README.md b/README.md
--- a/README.md
+++ b/README.md
@@ -1,2 +1,3 @@
+entry_service.delete_entry
 # Journal App
</pr_diff>"""


@pytest.mark.unit
class TestCheckIndicatorsPass:
    """Tests for successful indicator matching."""

    def test_all_pass_indicators_found(self):
        req = _make_requirement(
            pass_indicators=["import logging", "logging.basicConfig"],
        )
        result = check_indicators(_PASSING_DIFF, req)
        assert result.passed is True
        assert "import logging" in result.matched_pass
        assert "logging.basicConfig" in result.matched_pass
        assert result.missing_pass == []
        assert result.matched_fail == []

    def test_single_pass_indicator(self):
        req = _make_requirement(pass_indicators=["import logging"])
        result = check_indicators(_PASSING_DIFF, req)
        assert result.passed is True

    def test_case_insensitive_matching(self):
        req = _make_requirement(pass_indicators=["IMPORT LOGGING"])
        result = check_indicators(_PASSING_DIFF, req)
        assert result.passed is True


@pytest.mark.unit
class TestCheckIndicatorsFail:
    """Tests for failed indicator matching."""

    def test_missing_one_pass_indicator_still_passes(self):
        """Indicators are alternatives — only one needs to match."""
        req = _make_requirement(
            pass_indicators=["import logging", "import structlog"],
        )
        result = check_indicators(_PASSING_DIFF, req)
        assert result.passed is True
        assert "import logging" in result.matched_pass

    def test_no_pass_indicators_matched(self):
        """When NONE of the indicators match, it fails."""
        req = _make_requirement(
            pass_indicators=["import structlog", "structlog.configure"],
        )
        result = check_indicators(_PASSING_DIFF, req)
        assert result.passed is False
        assert "import structlog" in result.missing_pass

    def test_fail_indicator_found(self):
        req = _make_requirement(
            pass_indicators=["import logging"],
            fail_indicators=["# TODO (Task 1): Configure logging here."],
        )
        result = check_indicators(_FAILING_DIFF_WITH_STUB, req)
        assert result.passed is False
        assert len(result.matched_fail) == 1
        assert "starter/placeholder" in result.reason

    def test_fail_indicator_takes_priority_over_pass(self):
        """Even if pass indicators are present, fail indicators cause failure."""
        req = _make_requirement(
            pass_indicators=["import logging"],
            fail_indicators=["# TODO (Task 1): Configure logging here."],
        )
        result = check_indicators(_FAILING_DIFF_WITH_STUB, req)
        assert result.passed is False
        assert result.matched_fail  # fail indicator was found

    def test_no_pass_indicators_defined(self):
        req = _make_requirement(pass_indicators=None)
        result = check_indicators(_PASSING_DIFF, req)
        assert result.passed is False
        assert "No pass indicators" in result.reason

    def test_empty_pass_indicators(self):
        req = _make_requirement(pass_indicators=[])
        result = check_indicators(_PASSING_DIFF, req)
        assert result.passed is False


@pytest.mark.unit
class TestCheckIndicatorsLineScoping:
    """Tests for added-lines-only matching."""

    def test_does_not_match_removed_lines(self):
        """Indicators in removed (-) lines should not count."""
        req = _make_requirement(
            pass_indicators=["import logging", "logging.basicConfig"],
        )
        result = check_indicators(_DIFF_WITH_REMOVED_LINES, req)
        # "import logging" only appears in removed lines
        assert result.passed is False
        assert "import logging" in result.missing_pass

    def test_matches_added_lines(self):
        req = _make_requirement(
            pass_indicators=["import structlog", "structlog.configure"],
        )
        result = check_indicators(_DIFF_WITH_REMOVED_LINES, req)
        assert result.passed is True


@pytest.mark.unit
class TestCheckIndicatorsFileScoping:
    """Tests for expected_files scoping."""

    def test_scoped_to_expected_files(self):
        """Only match indicators in expected files."""
        req = _make_requirement(
            pass_indicators=["entry_service.get_entry", "status_code=404"],
            expected_files=["api/routers/journal_router.py"],
        )
        result = check_indicators(_MULTI_FILE_DIFF, req)
        assert result.passed is True

    def test_indicator_in_wrong_file_not_matched(self):
        """Indicator only in a non-expected file doesn't count as matched."""
        req = _make_requirement(
            pass_indicators=["entry_service.delete_entry"],
            expected_files=["api/routers/journal_router.py"],
        )
        result = check_indicators(_MULTI_FILE_DIFF, req)
        # delete_entry only appears in README.md, not in the expected file
        assert result.passed is False
        assert "entry_service.delete_entry" in result.missing_pass

    def test_no_expected_files_searches_all(self):
        """Without expected_files, all files are searched."""
        req = _make_requirement(
            pass_indicators=[
                "entry_service.get_entry",
                "entry_service.delete_entry",
            ],
        )
        result = check_indicators(_MULTI_FILE_DIFF, req)
        assert result.passed is True


@pytest.mark.unit
class TestCheckIndicatorsRealPhase3:
    """Test with real Phase 3 requirement indicator sets."""

    def test_logging_requirement_passes(self):
        """Simulates a real journal-pr-logging submission."""
        req = _make_requirement(
            pass_indicators=[
                "import logging",
                "logging.basicConfig",
                "logging.getLogger",
            ],
            fail_indicators=[
                "# TODO (Task 1): Configure logging here.",
            ],
            expected_files=["api/main.py"],
        )
        diff = """\
<pr_diff>
diff --git a/api/main.py b/api/main.py
--- a/api/main.py
+++ b/api/main.py
@@ -1,2 +1,7 @@
+import logging
+
+logging.basicConfig(level=logging.INFO)
+logger = logging.getLogger(__name__)
+logger.info("Starting app")
 from fastapi import FastAPI
</pr_diff>"""
        result = check_indicators(diff, req)
        assert result.passed is True

    def test_cloud_cli_requirement_passes(self):
        """Simulates a real journal-pr-cloud-cli submission."""
        req = _make_requirement(
            pass_indicators=[
                '"ghcr.io/devcontainers/features/azure-cli:1"',
            ],
            fail_indicators=[
                '// "ghcr.io/devcontainers/features/azure-cli:1"',
            ],
            expected_files=[".devcontainer/devcontainer.json"],
        )
        diff = """\
<pr_diff>
diff --git a/.devcontainer/devcontainer.json b/.devcontainer/devcontainer.json
--- a/.devcontainer/devcontainer.json
+++ b/.devcontainer/devcontainer.json
@@ -5,3 +5,3 @@
-    // "ghcr.io/devcontainers/features/azure-cli:1": {}
+    "ghcr.io/devcontainers/features/azure-cli:1": {}
</pr_diff>"""
        result = check_indicators(diff, req)
        assert result.passed is True

    def test_cloud_cli_still_commented_fails(self):
        """CLI still commented out should fail."""
        req = _make_requirement(
            pass_indicators=[
                '"ghcr.io/devcontainers/features/azure-cli:1"',
            ],
            fail_indicators=[
                '// "ghcr.io/devcontainers/features/azure-cli:1"',
            ],
            expected_files=[".devcontainer/devcontainer.json"],
        )
        diff = """\
<pr_diff>
diff --git a/.devcontainer/devcontainer.json b/.devcontainer/devcontainer.json
--- a/.devcontainer/devcontainer.json
+++ b/.devcontainer/devcontainer.json
@@ -5,3 +5,3 @@
+    // "ghcr.io/devcontainers/features/azure-cli:1": {}
</pr_diff>"""
        result = check_indicators(diff, req)
        assert result.passed is False
        assert result.matched_fail
