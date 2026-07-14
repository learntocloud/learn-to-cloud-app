"""Unit tests for verification-attempt snapshot/hash helpers."""

from __future__ import annotations

import pytest

from learn_to_cloud_shared.testing.requirement_factories import (
    journal_api_verifier_requirement,
    repo_fork_requirement,
)
from learn_to_cloud_shared.verification_attempt_snapshot import (
    ATTEMPT_PAYLOAD_VERSION,
    SUPPORTED_PAYLOAD_VERSIONS,
    AttemptSnapshotError,
    build_requirement_snapshot,
    compute_snapshot_hash,
    deserialize_requirement_snapshot,
    validate_snapshot_integrity,
)


def test_payload_version_is_supported() -> None:
    assert ATTEMPT_PAYLOAD_VERSION in SUPPORTED_PAYLOAD_VERSIONS


def test_snapshot_round_trips_to_typed_requirement() -> None:
    requirement = repo_fork_requirement(slug="fork", required_repo="owner/repo")
    snapshot = build_requirement_snapshot(requirement)
    restored = deserialize_requirement_snapshot(snapshot)
    assert restored == requirement


def test_hash_is_order_independent() -> None:
    requirement = journal_api_verifier_requirement(slug="journal")
    snapshot = build_requirement_snapshot(requirement)
    reordered = dict(reversed(list(snapshot.items())))
    assert compute_snapshot_hash(snapshot) == compute_snapshot_hash(reordered)


def test_validate_snapshot_integrity_accepts_matching_hash() -> None:
    requirement = repo_fork_requirement(slug="fork", required_repo="owner/repo")
    snapshot = build_requirement_snapshot(requirement)
    snapshot_hash = compute_snapshot_hash(snapshot)
    restored = validate_snapshot_integrity(
        snapshot=snapshot,
        snapshot_hash=snapshot_hash,
    )
    assert restored == requirement


def test_validate_snapshot_integrity_rejects_hash_mismatch() -> None:
    requirement = repo_fork_requirement(slug="fork", required_repo="owner/repo")
    snapshot = build_requirement_snapshot(requirement)
    with pytest.raises(AttemptSnapshotError, match="hash"):
        validate_snapshot_integrity(snapshot=snapshot, snapshot_hash="deadbeef")


def test_validate_snapshot_integrity_rejects_missing_snapshot() -> None:
    with pytest.raises(AttemptSnapshotError, match="missing requirement_snapshot"):
        validate_snapshot_integrity(snapshot=None, snapshot_hash="abc")


def test_validate_snapshot_integrity_rejects_missing_hash() -> None:
    requirement = repo_fork_requirement(slug="fork", required_repo="owner/repo")
    snapshot = build_requirement_snapshot(requirement)
    with pytest.raises(AttemptSnapshotError, match="missing requirement_snapshot_hash"):
        validate_snapshot_integrity(snapshot=snapshot, snapshot_hash=None)


def test_reconstructed_snapshot_is_not_runnable() -> None:
    # The reconstructed backfill shape carries reconciliation metadata, not a
    # runnable typed requirement, so it must be rejected.
    reconstructed = {
        "uuid": "11111111-1111-1111-1111-111111111111",
        "slug": "legacy",
        "name": "Legacy",
        "submission_type": "repo_fork",
        "submission_value_kind": "github_url",
        "reconstructed": True,
    }
    with pytest.raises(AttemptSnapshotError):
        deserialize_requirement_snapshot(reconstructed)
