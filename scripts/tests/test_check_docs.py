from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import check_docs


class CheckDocsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.repo_root = Path(self.temporary_directory.name)
        self.docs_root = self.repo_root / "docs"
        self.scaling_index = self.docs_root / "scaling-with-github" / "index.html"
        self.scaling_index.parent.mkdir(parents=True)
        self.scaling_index.write_text("<h1 id='slides'>Slides</h1>", encoding="utf-8")

        patcher = patch.multiple(
            check_docs,
            REPO_ROOT=self.repo_root,
            DOCS_ROOT=self.docs_root,
            REQUIRED_ENTRYPOINTS=(self.docs_root / "index.md", self.scaling_index),
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_accepts_valid_pages_links_and_fragments(self) -> None:
        (self.docs_root / "index.md").write_text(
            "# Home\n\n[Guide](guide.html#details)\n[Slides](scaling-with-github/)\n",
            encoding="utf-8",
        )
        (self.docs_root / "guide.md").write_text(
            "# Guide\n\n## Details\n", encoding="utf-8"
        )

        self.assertEqual(check_docs.validate_docs(), [])

    def test_reports_missing_local_target(self) -> None:
        (self.docs_root / "index.md").write_text(
            "# Home\n\n[Missing](missing.html)\n", encoding="utf-8"
        )

        errors = check_docs.validate_docs()

        self.assertEqual(len(errors), 1)
        self.assertIn("missing target", errors[0])

    def test_reports_missing_fragment(self) -> None:
        (self.docs_root / "index.md").write_text(
            "# Home\n\n[Guide](guide.html#missing)\n", encoding="utf-8"
        )
        (self.docs_root / "guide.md").write_text("# Guide\n", encoding="utf-8")

        errors = check_docs.validate_docs()

        self.assertEqual(len(errors), 1)
        self.assertIn("missing fragment", errors[0])

    def test_reports_links_that_escape_repository(self) -> None:
        (self.docs_root / "index.md").write_text(
            "# Home\n\n[Outside](../../outside.md)\n", encoding="utf-8"
        )

        errors = check_docs.validate_docs()

        self.assertEqual(len(errors), 1)
        self.assertIn("link escapes repo", errors[0])


if __name__ == "__main__":
    unittest.main()
