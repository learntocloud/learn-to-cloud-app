"""Complete, bounded evidence selection, collection, and prompt validation."""

from __future__ import annotations

from collections.abc import Iterable
from hashlib import sha256

from opentelemetry import trace

from learn_to_cloud.schemas.base import FrozenModel
from learn_to_cloud.schemas.verification import ValidationResult
from learn_to_cloud.verification.tasks.base import (
    EvidenceBundle,
    EvidenceItem,
    EvidencePolicy,
    VerificationTask,
)

EVIDENCE_ERROR_CODES = frozenset(
    {
        "evidence.required_missing",
        "evidence.file_limit",
        "evidence.item_limit",
        "evidence.total_limit",
        "evidence.selection",
        "evidence.configuration",
    }
)


class EvidenceError(ValueError):
    """A bounded evidence decision, not a partial grading packet."""

    def __init__(self, code: str, *, missing: Iterable[str] = ()) -> None:
        if code not in EVIDENCE_ERROR_CODES:
            raise ValueError("Unknown evidence reason")
        super().__init__(code)
        self.code = code
        self.missing = tuple(missing)
        self.recorded = False

    def to_validation_result(self) -> ValidationResult:
        if self.code == "evidence.required_missing":
            message = "Missing required evidence: " + ", ".join(self.missing) + "."
        else:
            message = (
                "Your work was not judged. The verifier could not assemble the "
                "required evidence. Retrying unchanged may not help; report this "
                "issue so the service can be fixed."
            )
        return ValidationResult(
            is_valid=False,
            message=message,
            verification_completed=self.code == "evidence.required_missing",
            error_code=self.code,
        )


class EvidenceSelection(FrozenModel):
    """Resolved inventory of all selected work and named optional presence."""

    paths: list[str]
    optional_presence: dict[str, bool]


def record_evidence_decision(
    reason: str,
    *,
    selected_count: int = 0,
    collected_count: int = 0,
    total_bytes: int = 0,
) -> None:
    """Emit only fixed decision labels and aggregate numeric measurements."""
    if reason not in EVIDENCE_ERROR_CODES | {"complete"}:
        raise ValueError("Unknown evidence telemetry reason")
    outcome = {
        "complete": "complete",
        "evidence.required_missing": "required_missing",
    }.get(reason, "incomplete")
    trace.get_current_span().add_event(
        "verification.evidence.assembled",
        {
            "evidence.outcome": outcome,
            "evidence.reason": reason,
            "evidence.selected_count": selected_count,
            "evidence.collected_count": collected_count,
            "evidence.total_bytes": total_bytes,
        },
    )


def _valid_path(path: str) -> bool:
    return (
        bool(path)
        and not path.startswith("/")
        and "\\" not in path
        and all(part not in {"", ".", ".."} for part in path.split("/"))
    )


def validate_evidence_policy(policy: EvidencePolicy) -> None:
    """Reject contradictory configuration independently of learner content."""
    named = [*policy.required_files, *policy.optional_files]
    if (
        min(policy.max_files, policy.max_file_size_bytes, policy.max_total_bytes) <= 0
        or len(named) != len(set(named))
        or any(not _valid_path(path) for path in named)
    ):
        raise EvidenceError("evidence.configuration")


def missing_required_evidence(
    paths: Iterable[str],
    policy: EvidencePolicy,
) -> list[str]:
    inventory = set(paths)
    return [path for path in policy.required_files if path not in inventory]


def _allowed_path(path: str, policy: EvidencePolicy) -> bool:
    return _valid_path(path) and (
        path in policy.required_files or path in policy.optional_files
    )


def resolve_evidence_selection(
    all_files: Iterable[str],
    task: VerificationTask,
) -> EvidenceSelection:
    """Select the whole published contract from a trustworthy inventory."""
    policy = task.evidence
    validate_evidence_policy(policy)
    inventory = set(all_files)
    missing = missing_required_evidence(inventory, policy)
    if missing:
        raise EvidenceError("evidence.required_missing", missing=missing)
    return EvidenceSelection(
        paths=sorted(path for path in inventory if _allowed_path(path, policy)),
        optional_presence={path: path in inventory for path in policy.optional_files},
    )


def validate_evidence_bundle(task: VerificationTask, bundle: EvidenceBundle) -> None:
    """Revalidate full content and contract at the actual prompt boundary."""
    policy = task.evidence
    validate_evidence_policy(policy)
    paths = [item.path for item in bundle.items]
    selected = bundle.selected_paths
    if (
        bundle.task_id != task.id
        or not paths
        or len(paths) != len(set(paths))
        or len(selected) != len(set(selected))
        or set(paths) != set(selected)
        or any(not _allowed_path(path, policy) for path in paths)
        or missing_required_evidence(paths, policy)
    ):
        raise EvidenceError("evidence.selection")
    expected_presence = {path: path in paths for path in policy.optional_files}
    if bundle.optional_presence != expected_presence:
        raise EvidenceError("evidence.selection")
    if len(paths) > policy.max_files:
        raise EvidenceError("evidence.file_limit")
    total = 0
    for item in bundle.items:
        encoded = item.content.encode("utf-8")
        if item.truncated or item.sha256 != sha256(encoded).hexdigest():
            raise EvidenceError("evidence.selection")
        if len(encoded) > policy.max_file_size_bytes:
            raise EvidenceError("evidence.item_limit")
        total += len(encoded)
    if total > policy.max_total_bytes:
        raise EvidenceError("evidence.total_limit")
    if total != bundle.total_bytes:
        raise EvidenceError("evidence.selection")


def _assemble(
    task: VerificationTask,
    pairs: list[tuple[str, str]],
    selection: EvidenceSelection,
) -> EvidenceBundle:
    policy = task.evidence
    if len(selection.paths) > policy.max_files:
        raise EvidenceError("evidence.file_limit")
    items: list[EvidenceItem] = []
    total = 0
    for path, content in pairs:
        encoded = content.encode("utf-8")
        if len(encoded) > policy.max_file_size_bytes:
            raise EvidenceError("evidence.item_limit")
        total += len(encoded)
        if total > policy.max_total_bytes:
            raise EvidenceError("evidence.total_limit")
        items.append(
            EvidenceItem(
                path=path,
                content=content,
                sha256=sha256(encoded).hexdigest(),
            )
        )
    bundle = EvidenceBundle(
        task_id=task.id,
        source=policy.source,
        items=items,
        total_bytes=total,
        selected_paths=selection.paths,
        optional_presence=selection.optional_presence,
    )
    validate_evidence_bundle(task, bundle)
    return bundle


def apply_evidence_cap(
    task: VerificationTask,
    pairs: Iterable[tuple[str, str]],
) -> EvidenceBundle:
    """Collect complete items or reject the packet; never truncate or drop."""
    collected = list(pairs)
    try:
        selection = resolve_evidence_selection((path for path, _ in collected), task)
        bundle = _assemble(task, collected, selection)
    except EvidenceError as exc:
        record_evidence_decision(
            exc.code,
            selected_count=len(collected),
            collected_count=len(collected),
            total_bytes=sum(len(content.encode("utf-8")) for _, content in collected),
        )
        exc.recorded = True
        raise
    record_evidence_decision(
        "complete",
        selected_count=len(bundle.items),
        collected_count=len(bundle.items),
        total_bytes=bundle.total_bytes,
    )
    return bundle


def collect_submitted_text_evidence(
    task: VerificationTask,
    text: str,
    path: str = "submission.txt",
) -> EvidenceBundle:
    """Wrap the full submitted text as an evidence bundle."""
    return apply_evidence_cap(task, [(path, text)])
