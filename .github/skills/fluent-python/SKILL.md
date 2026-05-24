---
name: fluent-python
description: Map concepts, issues, and code changes in this repo to specific chapters and pages of Fluent Python, 2nd edition (Luciano Ramalho). Use when the user wants to ground a task in the underlying Python concept, e.g. "where is this in fluent python?", "what should I read for #N?", "point me at the book for X", or before designing a non-trivial API/data model/concurrency change.
---

# Fluent Python Concept Mapping

Maps work happening in `learn-to-cloud-app` to the relevant sections in **Fluent Python, 2nd ed. (Ramalho, O'Reilly 2022)** by reading directly from the EPUB.

The EPUB lives at `.github/skills/fluent-python/fluent-book.epub` (gitignored). It is a standard zip file containing structured HTML chapters, a navigable table of contents, and a back-of-book index.

---

## When to Use

- User asks "where is this in fluent python?", "what should I read for this?", "what's the book section on X?"
- User references an issue or PR and asks for the underlying concept
- Before designing a non-trivial change involving: protocols/ABCs, async, generators, dataclasses, descriptors, type hints, operator overloading, sequence/mapping APIs, or metaclasses
- After a code review surfaces a conceptual gap

Do NOT use for: project-specific deployment, Azure, or business-logic questions.

---

## How to Look Up Concepts (Two-Pass Approach)

You have direct access to the book. Use this two-pass process to find and verify relevant sections.

### Pass 1: Narrow down candidates

Run a single Python script via bash that does both of these in one shot:

1. **Search the back index** (`OEBPS/ix01.html`) for the concept and synonyms.
2. **Search the TOC** (`OEBPS/toc01.html`) for matching chapter/section headings.

Use this script pattern:

```python
import zipfile, re
from html.parser import HTMLParser

EPUB = '.github/skills/fluent-python/fluent-book.epub'

class TextExtractor(HTMLParser):
    """Strip HTML tags, return plain text."""
    def __init__(self):
        super().__init__()
        self.parts = []
    def handle_data(self, data):
        self.parts.append(data)
    def get_text(self):
        return ' '.join(self.parts)

def strip_html(html):
    t = TextExtractor()
    t.feed(html)
    return t.get_text()

def search_index(zf, terms):
    """Search the back index for terms. Returns list of (term, section_title, href)."""
    ix = zf.read('OEBPS/ix01.html').decode('utf-8')
    results = []
    # Parse at the <li> level to associate terms with their locator links
    for li_match in re.finditer(r'<li>(.*?)</li>', ix, re.DOTALL):
        li_html = li_match.group(1)
        li_text = strip_html(li_html).lower()
        for term in terms:
            if term.lower() in li_text:
                # Extract all locator links from this index entry
                for link in re.finditer(
                    r'<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
                    li_html, re.DOTALL
                ):
                    href, link_text = link.group(1), strip_html(link.group(2))
                    results.append((term, link_text, href))
                break
    return results

def search_toc(zf, terms):
    """Search TOC headings for terms. Returns list of (heading, href)."""
    toc = zf.read('OEBPS/toc01.html').decode('utf-8')
    results = []
    for link in re.finditer(
        r'<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', toc, re.DOTALL
    ):
        href, heading = link.group(1), strip_html(link.group(2))
        heading_lower = heading.lower()
        for term in terms:
            if term.lower() in heading_lower:
                results.append((heading, href))
                break
    return results

# --- Usage ---
zf = zipfile.ZipFile(EPUB)

# Adapt these terms to the user's concept + synonyms
terms = ['protocol', 'structural typing', 'duck typing']

print('=== INDEX MATCHES ===')
for term, section, href in search_index(zf, terms):
    print(f'  [{term}] {section} -> {href}')

print()
print('=== TOC MATCHES ===')
for heading, href in search_toc(zf, terms):
    print(f'  {heading} -> {href}')
```

**Choosing search terms:** Always include the literal concept plus 1-2 synonyms. Common synonyms:
- `dataclass` / `data class` / `data class builder`
- `Protocol` / `structural typing` / `static protocol`
- `async def` / `coroutine` / `asyncio`
- `decorator` / `closure` / `functools`
- `generator` / `yield` / `iterator`
- `ABC` / `abstract base class` / `goose typing`

### Pass 2: Read and verify candidate sections

For each promising candidate from Pass 1, extract only the **bounded section** (from one heading to the next heading of the same or higher level). Never read an entire chapter.

```python
def extract_section(zf, href):
    """Extract the section around an anchor from a chapter file.

    Returns clean text bounded by the nearest enclosing heading
    to the next heading of equal or higher level.
    """
    # Split href into file and optional anchor
    if '#' in href:
        filename, anchor = href.split('#', 1)
    else:
        filename, anchor = href, None

    filepath = filename if filename.startswith('OEBPS/') else f'OEBPS/{filename}'
    html = zf.read(filepath).decode('utf-8')

    if anchor:
        # Find the anchor position
        anchor_patterns = [
            f'id="{anchor}"',
            f"id='{anchor}'",
        ]
        pos = -1
        for pat in anchor_patterns:
            pos = html.find(pat)
            if pos != -1:
                break

        if pos == -1:
            # Anchor not found; fall back to start of file
            pos = 0
    else:
        pos = 0

    # Walk backward to find the enclosing heading
    heading_pattern = re.compile(r'<(h[1-3])\b[^>]*>', re.IGNORECASE)
    search_region = html[:pos]
    headings_before = list(heading_pattern.finditer(search_region))

    if headings_before:
        last_heading = headings_before[-1]
        section_start = last_heading.start()
        enclosing_level = int(last_heading.group(1)[1])
    else:
        section_start = pos
        enclosing_level = 1

    # Walk forward to find the next heading of same or higher level
    remaining = html[section_start:]
    end_pattern = re.compile(
        r'<(h[1-' + str(enclosing_level) + r'])\b[^>]*>',
        re.IGNORECASE
    )
    # Skip the first match (our own heading)
    matches = list(end_pattern.finditer(remaining))
    if len(matches) > 1:
        section_end = section_start + matches[1].start()
    else:
        # Take a reasonable chunk (don't read to end of file)
        section_end = min(section_start + 15000, len(html))

    section_html = html[section_start:section_end]
    return strip_html(section_html)

# --- Usage ---
# Read the top 2-4 candidates from Pass 1
for href in candidate_hrefs[:4]:
    text = extract_section(zf, href)
    # Truncate to ~3000 chars for review
    print(text[:3000])
    print('---')
```

After reading the sections, determine which one best answers the user's question.

### Priority ranking for candidates

1. **Exact index match** (term appears in back index, links to specific anchor)
2. **TOC heading match** (section title contains the concept)
3. **Synonym/fuzzy match** (related term found in index or TOC)
4. **Hint map match** (see Quick Reference Hints below; use only as a starting point, always verify)

---

## Response Rules

1. **Cite chapter and section title.** Example: "Ch. 13, Static Protocols"
2. **Keep quotations minimal.** One short sentence or phrase max to illustrate the key point. Do not reproduce paragraphs.
3. **Summarize, don't paraphrase.** Describe what the section covers and why it is relevant.
4. **Tie back to the repo.** Connect the section to a concrete file, issue, or symbol.
5. **Admit gaps.** If the concept is not covered in the book, say so and suggest the nearest neighbor.

---

## Response Template

```
**Concept:** <one-line restatement of the underlying Python concept>

**Primary:** Ch. N, "<Section title>"
<one sentence on what this section covers and why it's relevant>

**Also useful (optional):** Ch. N, "<Section title>"

**Tie-in:** <repo file or issue> -- <one sentence connecting the section to the concrete change>
```

Keep the entire reply under ~120 words unless the user asks for more depth.

---

## Quick Reference Hints

These hints help seed your search terms. They are approximate starting points, not authoritative answers. Always verify against the actual EPUB content using the two-pass process above.

| Repo area | Likely chapters |
|---|---|
| `packages/learn-to-cloud-shared/src/.../verification/` enums and result types | Ch. 5, Ch. 13 |
| `api/src/learn_to_cloud/services/` async services | Ch. 19, Ch. 21 |
| `api/src/learn_to_cloud/repositories/` repository pattern | Ch. 8 (generics), Ch. 13 (protocols) |
| `apps/verification-functions/` handler dispatch | Ch. 9 (single dispatch), Ch. 13 (protocols) |
| FastAPI routes in `api/src/learn_to_cloud/api/` | Ch. 21, Ch. 9 |

---

## Fallback Behavior

If the EPUB file is missing or cannot be read:
1. Say explicitly: "The EPUB is not available; falling back to the reference hints."
2. Use the Quick Reference Hints table above to give the best guess.
3. Clearly mark the answer as unverified.

---

## Out of Scope

- Topics not covered by Fluent Python 2e (Pydantic v2 internals, SQLAlchemy 2.x specifics, Alembic, Azure SDKs, FastAPI beyond the brief example). Say so explicitly and suggest the nearest conceptual neighbor.
- Reproducing large portions of the book. Keep quotations to a single short sentence max.
- Edition mismatches: this is the 2nd edition EPUB only.

---

## Trigger Phrases

- "where is this in fluent python"
- "what should I read for #<N>"
- "fluent python on <topic>"
- "point me at the book for <topic>"
- "what's the concept behind <task>"
- "ground this in the book"
