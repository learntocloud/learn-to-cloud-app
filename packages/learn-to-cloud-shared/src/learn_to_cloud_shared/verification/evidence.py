"""Shared bounded repository evidence collection helpers."""

from __future__ import annotations

from hashlib import sha256

import httpx
from opentelemetry import trace

from learn_to_cloud_shared.core.github_client import (
    get_github_client as _get_github_client,
)
from learn_to_cloud_shared.verification.github_profile import get_github_headers
from learn_to_cloud_shared.verification.tasks.base import (
    EvidenceBundle,
    EvidenceItem,
    VerificationTask,
)


async def fetch_repo_file_content(
    owner: str,
    repo: str,
    path: str,
    branch: str = "main",
) -> str | None:
    """Fetch raw repository file content from GitHub."""
    client = await _get_github_client()
    headers = get_github_headers()

    url = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{path}"
    try:
        response = await client.get(url, headers=headers)
        response.raise_for_status()
    except httpx.HTTPStatusError:
        span = trace.get_current_span()
        span.add_event(
            "repo_file_fetch_failed",
            {"owner": owner, "repo": repo, "path": path},
        )
        return None

    return response.text


async def collect_repo_file_evidence(
    owner: str,
    repo: str,
    paths: list[str],
    task: VerificationTask,
    branch: str = "main",
) -> EvidenceBundle:
    """Collect repository files within a task's evidence limits."""
    items: list[EvidenceItem] = []
    total_bytes = 0

    for path in list(dict.fromkeys(paths))[: task.evidence.max_files]:
        content = await fetch_repo_file_content(owner, repo, path, branch)
        if content is None:
            continue

        encoded = content.encode("utf-8")
        truncated = False
        if len(encoded) > task.evidence.max_file_size_bytes:
            content = truncate_to_bytes(content, task.evidence.max_file_size_bytes)
            encoded = content.encode("utf-8")
            truncated = True

        if total_bytes + len(encoded) > task.evidence.max_total_bytes:
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
        source=task.evidence.source,
        items=items,
        total_bytes=total_bytes,
    )


_TRUNCATION_MARKER = "\n\n[FILE TRUNCATED - exceeded size limit]"


def truncate_to_bytes(content: str, max_bytes: int) -> str:
    """Truncate content so its UTF-8 size, including the marker, fits in max_bytes."""
    marker_bytes = len(_TRUNCATION_MARKER.encode("utf-8"))
    budget = max(max_bytes - marker_bytes, 0)
    encoded = content.encode("utf-8")[:budget]
    return encoded.decode("utf-8", errors="ignore") + _TRUNCATION_MARKER
