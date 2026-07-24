"""Validate local links and GitHub Pages entrypoints under docs/."""

from __future__ import annotations

import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

REPO_ROOT = Path(__file__).resolve().parents[1]
DOCS_ROOT = REPO_ROOT / "docs"
PAGES_PREFIX = "/learn-to-cloud-app/"
REQUIRED_ENTRYPOINTS = (
    DOCS_ROOT / "index.md",
    DOCS_ROOT / "scaling-with-github" / "index.html",
)
MARKDOWN_LINK = re.compile(r"!?\[[^\]]*]\(([^)\s]+)(?:\s+[^)]*)?\)")
MARKDOWN_HEADING = re.compile(r"^#{1,6}\s+(.+?)\s*#*\s*$", re.MULTILINE)


class LinkParser(HTMLParser):
    """Collect links and anchors from an HTML document."""

    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []
        self.anchors: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        for name in ("id", "name"):
            if value := attributes.get(name):
                self.anchors.add(value)
        for name in ("href", "src"):
            if value := attributes.get(name):
                self.links.append(value)


def markdown_anchors(content: str) -> set[str]:
    """Return GitHub-style heading anchors for Markdown content."""
    anchors: set[str] = set()
    for heading in MARKDOWN_HEADING.findall(content):
        anchor = re.sub(r"[^\w\- ]", "", heading.lower(), flags=re.UNICODE)
        anchors.add(re.sub(r"[\s\-]+", "-", anchor).strip("-"))
    return anchors


def links_and_anchors(path: Path) -> tuple[list[str], set[str]]:
    content = path.read_text(encoding="utf-8")
    if path.suffix == ".html":
        parser = LinkParser()
        parser.feed(content)
        return parser.links, parser.anchors
    return MARKDOWN_LINK.findall(content), markdown_anchors(content)


def resolve_target(source: Path, link_path: str) -> Path:
    decoded_path = unquote(link_path)
    if decoded_path.startswith(PAGES_PREFIX):
        target = DOCS_ROOT / decoded_path.removeprefix(PAGES_PREFIX)
    elif decoded_path.startswith("/"):
        target = DOCS_ROOT / decoded_path.removeprefix("/")
    else:
        target = source.parent / decoded_path

    target = target.resolve()
    if target.suffix == ".html" and not target.exists():
        markdown_target = target.with_suffix(".md")
        if markdown_target.exists():
            target = markdown_target
    if target.is_dir():
        for index_name in ("index.md", "index.html"):
            index = target / index_name
            if index.exists():
                return index
    return target


def validate_docs() -> list[str]:
    """Return validation errors for the documentation tree."""
    errors: list[str] = []
    for entrypoint in REQUIRED_ENTRYPOINTS:
        if not entrypoint.is_file():
            errors.append(f"missing required Pages entrypoint: {entrypoint}")

    documents = sorted((*DOCS_ROOT.rglob("*.md"), *DOCS_ROOT.rglob("*.html")))
    for source in documents:
        links, _ = links_and_anchors(source)
        for link in links:
            parsed = urlsplit(link)
            if parsed.scheme or parsed.netloc:
                continue
            if not parsed.path:
                target = source
            else:
                target = resolve_target(source, parsed.path)

            try:
                target.relative_to(REPO_ROOT)
            except ValueError:
                errors.append(
                    f"{source.relative_to(REPO_ROOT)}: link escapes repo: {link}"
                )
                continue

            if not target.is_file():
                errors.append(
                    f"{source.relative_to(REPO_ROOT)}: missing target for {link}"
                )
                continue

            if parsed.fragment and target.suffix in {".md", ".html"}:
                _, anchors = links_and_anchors(target)
                if unquote(parsed.fragment) not in anchors:
                    errors.append(
                        f"{source.relative_to(REPO_ROOT)}: missing fragment for {link}"
                    )
    return errors


def main() -> int:
    errors = validate_docs()
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    document_count = sum(1 for _ in DOCS_ROOT.rglob("*") if _.is_file())
    print(f"Documentation links valid across {document_count} files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
