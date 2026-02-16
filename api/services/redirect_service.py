"""Legacy URL redirect resolution service.

Resolves legacy ``/phaseN`` paths to their canonical ``/phase/N`` form,
including fuzzy topic-slug matching against current content.
"""

from __future__ import annotations

import re
from functools import lru_cache

_legacy_phase_path_re = re.compile(r"^/phase[-_]?(?P<phase_id>\d+)(?P<rest>/.*)?$")


def _normalize_legacy_slug(slug: str) -> str:
    """Strip non-alphanumeric chars so fuzzy legacy slugs can match canonical ones."""
    slug = slug.lower()
    if slug.endswith(".html"):
        slug = slug.removesuffix(".html")
    return re.sub(r"[^a-z0-9]+", "", slug)


@lru_cache(maxsize=1)
def _topic_slug_aliases_by_phase() -> dict[str, dict[str, str]]:
    """Build a mapping of legacy topic slugs -> current topic slugs per phase.

    Note:
        Cached for the lifetime of the process. If content YAML changes, a server
        restart is required for this mapping to update.
    """
    # Deferred import to avoid circular dependency with services.content_service.
    from services.content_service import get_all_phases

    aliases: dict[str, dict[str, str]] = {}
    for phase in get_all_phases():
        phase_id = str(phase.id)
        phase_aliases: dict[str, str] = {}
        for topic_slug in phase.topic_slugs:
            phase_aliases[_normalize_legacy_slug(topic_slug)] = topic_slug
        aliases[phase_id] = phase_aliases

    # Known legacy slugs from older docs / bookmarks.
    manual_aliases: dict[str, dict[str, str]] = {
        "1": {
            "ctf": "ctf-lab",
            "versioncontrol": "developer-setup",
        },
        "2": {
            "networkingfundamentals": "fundamentals",
            "portsandprotocols": "protocols",
            "troubleshooting": "troubleshooting-lab",
        },
    }
    for phase_id, slug_map in manual_aliases.items():
        phase_aliases = aliases.setdefault(phase_id, {})
        for legacy_slug, canonical_slug in slug_map.items():
            phase_aliases[_normalize_legacy_slug(legacy_slug)] = canonical_slug
    return aliases


def resolve_legacy_phase_redirect(path: str) -> str | None:
    """Return the canonical redirect path for a legacy /phaseN URL, or None."""
    match = _legacy_phase_path_re.match(path)
    if not match or path.startswith("/phase/"):
        return None

    phase_id = match.group("phase_id")
    rest = match.group("rest") or ""

    # Normalize phase roots (/phase1 and /phase1/) to /phase/1.
    if rest in ("", "/"):
        return f"/phase/{phase_id}"

    # Try to map /phaseN/<topic> to /phase/N/<topic-slug>; otherwise
    # fall back to the phase root so we don't redirect to a 404 topic.
    parts = rest.lstrip("/").split("/")
    legacy_topic = parts[0]
    # Filter empty segments so double-slashes are normalised away.
    remainder = [p for p in parts[1:] if p]

    topic_aliases = _topic_slug_aliases_by_phase().get(str(phase_id), {})
    canonical_topic = topic_aliases.get(_normalize_legacy_slug(legacy_topic))
    if canonical_topic:
        target_path = f"/phase/{phase_id}/{canonical_topic}"
        if remainder:
            target_path = f"{target_path}/{'/'.join(remainder)}"
        return target_path

    return f"/phase/{phase_id}"
