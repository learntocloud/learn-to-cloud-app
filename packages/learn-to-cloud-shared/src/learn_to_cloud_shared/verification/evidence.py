"""Shared bounded evidence collection.

Split into three jobs so a phase composes them instead of each phase
carrying its own collector:

1. **cap** (:func:`apply_evidence_cap`) - given (path, content) pairs and a
   task's :class:`EvidencePolicy`, enforce ``max_files`` /
   ``max_file_size_bytes`` / ``max_total_bytes`` and build the
   :class:`EvidenceBundle`. No network.
2. **select/get-content**, keyed by :class:`EvidenceSource`: ``repo_files``
   supports exact paths or bounded path-pattern discovery before fetching from
   GitHub; ``submitted_text`` is a no-network passthrough. A phase may use
   either or both.
3. **selection** per phase lives with the profile/task (which paths, which
   source), not here.
"""

from __future__ import annotations

from collections.abc import Iterable
from hashlib import sha256

from learn_to_cloud_shared.verification.repo_files import RepoFiles
from learn_to_cloud_shared.verification.tasks.base import (
    EvidenceBundle,
    EvidenceItem,
    VerificationTask,
)


def apply_evidence_cap(
    task: VerificationTask,
    pairs: Iterable[tuple[str, str]],
) -> EvidenceBundle:
    """Build a bundle from (path, content) pairs within the task's caps.

    Deduplicates by path, keeps at most ``max_files``, truncates any item
    over ``max_file_size_bytes``, and stops once ``max_total_bytes`` would be
    exceeded. Pure and network-free so every source shares one cap policy.
    """
    policy = task.evidence
    items: list[EvidenceItem] = []
    total_bytes = 0
    seen: set[str] = set()

    for path, content in pairs:
        if path in seen:
            continue
        seen.add(path)
        if len(items) >= policy.max_files:
            break

        encoded = content.encode("utf-8")
        truncated = False
        if len(encoded) > policy.max_file_size_bytes:
            content = truncate_to_bytes(content, policy.max_file_size_bytes)
            encoded = content.encode("utf-8")
            truncated = True

        if total_bytes + len(encoded) > policy.max_total_bytes:
            break

        total_bytes += len(encoded)
        items.append(
            EvidenceItem(
                path=path,
                content=content,
                sha256=sha256(encoded).hexdigest(),
                truncated=truncated,
            )
        )

    return EvidenceBundle(
        task_id=task.id,
        source=policy.source,
        items=items,
        total_bytes=total_bytes,
    )


async def collect_repo_file_evidence(
    repo_files: RepoFiles,
    owner: str,
    repo: str,
    paths: list[str],
    task: VerificationTask,
    branch: str = "main",
) -> EvidenceBundle:
    """Fetch repository files (get-content) and apply the shared cap."""
    fetched: list[tuple[str, str]] = []
    for path in dict.fromkeys(paths):
        content = await repo_files.file(owner, repo, path, branch)
        if content is None:
            continue
        fetched.append((path, content))
    return apply_evidence_cap(task, fetched)


def select_repo_paths(
    all_files: Iterable[str],
    patterns: Iterable[str],
    *,
    max_files: int,
) -> list[str]:
    """Select exact paths first, then directory-prefix matches."""
    ordered_files = sorted(all_files, key=str.casefold)
    ordered_patterns = list(patterns)
    exact_patterns = [
        pattern for pattern in ordered_patterns if not pattern.endswith("/")
    ]
    directory_patterns = [
        pattern for pattern in ordered_patterns if pattern.endswith("/")
    ]
    selected: list[str] = []
    selected_normalized: set[str] = set()

    for pattern in exact_patterns:
        match = next(
            (
                path
                for path in ordered_files
                if path.casefold() == pattern.casefold()
                and path.casefold() not in selected_normalized
            ),
            None,
        )
        if match is not None:
            selected.append(match)
            selected_normalized.add(match.casefold())

    for path in ordered_files:
        normalized_path = path.casefold()
        if normalized_path in selected_normalized:
            continue
        if any(
            normalized_path.startswith(pattern.casefold())
            for pattern in directory_patterns
        ):
            selected.append(path)
            selected_normalized.add(normalized_path)
        if len(selected) >= max_files:
            break

    return selected[:max_files]


async def collect_repo_pattern_evidence(
    repo_files: RepoFiles,
    owner: str,
    repo: str,
    task: VerificationTask,
    branch: str = "main",
) -> EvidenceBundle:
    """Discover task path patterns in the tree, then fetch bounded evidence."""
    all_files = await repo_files.tree(owner, repo, branch)
    selected = select_repo_paths(
        all_files,
        task.evidence.path_patterns,
        max_files=task.evidence.max_files,
    )
    return await collect_repo_file_evidence(
        repo_files,
        owner,
        repo,
        selected,
        task,
        branch,
    )


def collect_submitted_text_evidence(
    task: VerificationTask,
    text: str,
    path: str = "submission.txt",
) -> EvidenceBundle:
    """Wrap free-form submitted text as evidence (no-network passthrough)."""
    return apply_evidence_cap(task, [(path, text)])


_TRUNCATION_MARKER = "\n\n[FILE TRUNCATED - exceeded size limit]"


def truncate_to_bytes(content: str, max_bytes: int) -> str:
    """Truncate content so its UTF-8 size, including the marker, fits in max_bytes."""
    marker_bytes = len(_TRUNCATION_MARKER.encode("utf-8"))
    budget = max(max_bytes - marker_bytes, 0)
    encoded = content.encode("utf-8")[:budget]
    return encoded.decode("utf-8", errors="ignore") + _TRUNCATION_MARKER
