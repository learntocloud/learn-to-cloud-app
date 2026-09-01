"""Canonical requirement-snapshot helpers for verification attempts.

An attempt row stores the *requirement definition* it was submitted against
(``requirement_snapshot``) plus a hash of that snapshot
(``requirement_snapshot_hash``) so the Functions role can run verification
without any curriculum grants. This module is the single source of truth for
how that snapshot is built, hashed, and validated so the API writer (a later
PR) and the Functions reader stay in exact agreement.

``ATTEMPT_PAYLOAD_VERSION`` is the contract version stamped on every
``submitted`` attempt. The prepare activity rejects any attempt whose stored
``payload_version`` this code cannot run, so an incompatible producer can never
be silently mis-executed.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping

from learn_to_cloud_shared.schemas import (
    HandsOnRequirement,
    HandsOnRequirementAdapter,
)

# Bump only alongside a breaking change to the snapshot/hash contract.
ATTEMPT_PAYLOAD_VERSION = 1

# Snapshot payload versions this code version can execute. Kept as a set so a
# future PR can widen support during a rolling deploy without a code branch.
SUPPORTED_PAYLOAD_VERSIONS: frozenset[int] = frozenset({ATTEMPT_PAYLOAD_VERSION})


class AttemptSnapshotError(ValueError):
    """The stored requirement snapshot is missing, malformed, or inconsistent."""


def build_requirement_snapshot(requirement: HandsOnRequirement) -> dict:
    """Serialize a typed requirement into its stored snapshot form."""
    return requirement.model_dump(mode="json")


def compute_snapshot_hash(snapshot: Mapping[str, object]) -> str:
    """Return the stable SHA-256 hash of a requirement snapshot.

    The snapshot is serialized with sorted keys and compact separators so the
    hash is independent of dict ordering and whitespace, matching whatever the
    producer computed at submission time.
    """
    canonical = json.dumps(
        dict(snapshot),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def deserialize_requirement_snapshot(
    snapshot: Mapping[str, object],
) -> HandsOnRequirement:
    """Rehydrate a typed requirement from a stored snapshot.

    Raises :class:`AttemptSnapshotError` when the snapshot does not deserialize
    into a known typed requirement (e.g. a reconstructed backfill row that only
    carries reconciliation metadata, not a runnable requirement definition).
    """
    try:
        return HandsOnRequirementAdapter.validate_python(dict(snapshot))
    except (ValueError, TypeError, KeyError) as exc:
        raise AttemptSnapshotError(
            f"requirement snapshot is not a runnable requirement: {exc}"
        ) from exc


def validate_snapshot_integrity(
    *,
    snapshot: Mapping[str, object] | None,
    snapshot_hash: str | None,
) -> HandsOnRequirement:
    """Validate a submitted snapshot's shape + hash and return the requirement.

    Enforces that the snapshot and its hash are both present and that the hash
    matches the snapshot's canonical form (guarding against a tampered or
    truncated row), then deserializes it into a typed requirement.
    """
    if snapshot is None:
        raise AttemptSnapshotError("submitted attempt is missing requirement_snapshot")
    if not snapshot_hash:
        raise AttemptSnapshotError(
            "submitted attempt is missing requirement_snapshot_hash"
        )
    expected = compute_snapshot_hash(snapshot)
    if expected != snapshot_hash:
        raise AttemptSnapshotError(
            "requirement_snapshot_hash does not match the stored snapshot"
        )
    return deserialize_requirement_snapshot(snapshot)
