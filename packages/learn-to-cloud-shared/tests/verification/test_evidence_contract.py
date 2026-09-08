"""Complete packet boundaries, published source rules, and safe telemetry."""

import json
from hashlib import sha256
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from pydantic import ValidationError

from learn_to_cloud_shared.schemas import ValidationResult
from learn_to_cloud_shared.verification import evidence as evidence_module
from learn_to_cloud_shared.verification import repo_files as repo_files_module
from learn_to_cloud_shared.verification.evidence import (
    EVIDENCE_ERROR_CODES,
    EvidenceError,
    apply_evidence_cap,
    collect_repo_file_evidence,
)
from learn_to_cloud_shared.verification.grading_requests import (
    LLMGradingRequest,
    build_repo_rubric_message,
    build_text_rubric_message,
    validate_grading_request,
)
from learn_to_cloud_shared.verification.repo_files import GitHubRepoFiles
from learn_to_cloud_shared.verification.security_scanning import (
    collect_security_scanning_evidence,
)
from learn_to_cloud_shared.verification.tasks import (
    CAREER_REFLECTION_RUBRIC_TASK,
    SECURITY_SCANNING_RUBRIC_TASK,
)
from learn_to_cloud_shared.verification.tasks.base import (
    EvidenceBundle,
)
from tests.fakes.repo_files import InMemoryRepoFiles

TASKS = [
    SECURITY_SCANNING_RUBRIC_TASK,
    CAREER_REFLECTION_RUBRIC_TASK,
]


def _with_policy(task, **updates):
    return task.model_copy(
        update={"evidence": task.evidence.model_copy(update=updates)}
    )


@pytest.mark.parametrize("task", TASKS, ids=lambda task: task.id)
def test_every_rubric_criterion_has_declared_evidence(task):
    groups = set(task.evidence.required_files) | set(task.evidence.optional_files)
    assert set(task.evidence.criterion_evidence) == {
        criterion.id for criterion in task.criteria
    }
    for paths in task.evidence.criterion_evidence.values():
        assert paths
        assert set(paths) <= groups
    assert task.grader.prompt_version == "2026-09-06"


@pytest.mark.parametrize(
    "missing", SECURITY_SCANNING_RUBRIC_TASK.evidence.required_files
)
async def test_proven_absence_names_canonical_work_without_reads(missing):
    task = SECURITY_SCANNING_RUBRIC_TASK
    files = dict.fromkeys(task.evidence.required_files, "complete")
    del files[missing]
    files.update(
        {".github/workflows/ci.yaml": "alternate", "requirements.txt": "alternate"}
    )
    repo = InMemoryRepoFiles(files)
    with pytest.raises(EvidenceError, match="evidence.required_missing") as caught:
        await collect_repo_file_evidence(repo, "owner", "repo", [], task)
    result = caught.value.to_validation_result()
    assert result.verification_completed
    assert missing in result.message
    assert not repo.file_reads


async def test_helpers_use_only_named_files_and_full_optional_support():
    task = SECURITY_SCANNING_RUBRIC_TASK
    selected = [*task.evidence.required_files, *task.evidence.optional_files]
    files = dict.fromkeys(selected, "完整\nimplementation")
    files.update(
        {
            "tests/test_api.py": "x" * 500_000,
            "api/uncollected.py": "x" * 500_000,
            ".github/workflows/ci.yaml": "x" * 500_000,
            "requirements.txt": "x" * 500_000,
        }
    )
    repo = InMemoryRepoFiles(files)
    bundle = await collect_security_scanning_evidence(
        "owner",
        "repo",
        repo_files=repo,
    )
    assert repo.file_reads == sorted(selected)
    assert all(item.content == "完整\nimplementation" for item in bundle.items)
    assert bundle.optional_presence == dict.fromkeys(task.evidence.optional_files, True)


@pytest.mark.parametrize("present", [False, True])
async def test_dependabot_presence_is_explicit_in_the_real_prompt(present):
    task = SECURITY_SCANNING_RUBRIC_TASK
    files = dict.fromkeys(task.evidence.required_files, "CodeQL")
    if present:
        files[task.evidence.optional_files[0]] = "version: 2\nupdates: []"
    files[".github/dependabot.yaml"] = "out of contract" * 50_000
    repo = InMemoryRepoFiles(files)
    bundle = await collect_security_scanning_evidence("owner", "repo", repo_files=repo)
    message = build_repo_rubric_message(
        requirement_slug="security-scanning",
        requirement_name="Security",
        deterministic_result=ValidationResult(is_valid=True, message="Passed"),
        owner="owner",
        repo="repo",
        task=task,
        evidence=bundle.model_dump(mode="json"),
    )
    payload = json.loads(message.split("\n\n", 1)[1])
    assert payload["evidence"]["optional_presence"] == {
        ".github/dependabot.yml": present
    }
    assert ".github/dependabot.yaml" not in repo.file_reads


async def test_oversized_optional_dependabot_blocks_whole_packet():
    task = SECURITY_SCANNING_RUBRIC_TASK
    repo = InMemoryRepoFiles(
        {
            task.evidence.required_files[0]: "CodeQL",
            task.evidence.optional_files[0]: "x"
            * (task.evidence.max_file_size_bytes + 1),
        }
    )
    with pytest.raises(EvidenceError, match="evidence.item_limit"):
        await collect_security_scanning_evidence("owner", "repo", repo_files=repo)


@pytest.mark.parametrize(("count", "code"), [(24, None), (25, "evidence.file_limit")])
async def test_selected_count_limit_precedes_any_file_read(count, code):
    files = {f"evidence-{i}.txt": "source" for i in range(count)}
    task = _with_policy(
        SECURITY_SCANNING_RUBRIC_TASK,
        required_files=list(files),
        optional_files=[],
        max_files=24,
    )
    repo = InMemoryRepoFiles(files)
    if code:
        with pytest.raises(EvidenceError, match=code):
            await collect_repo_file_evidence(repo, "owner", "repo", [], task)
        assert not repo.file_reads
    else:
        bundle = await collect_repo_file_evidence(repo, "owner", "repo", [], task)
        assert len(bundle.items) == count


@pytest.mark.parametrize("text", ['é"\\\n🦊', "x", ""])
def test_exact_utf8_byte_boundary_and_complete_json_round_trip(text):
    task = _with_policy(
        CAREER_REFLECTION_RUBRIC_TASK,
        max_file_size_bytes=max(1, len(text.encode("utf-8"))),
        max_total_bytes=max(1, len(text.encode("utf-8"))),
    )
    bundle = apply_evidence_cap(task, [("career-reflection.md", text)])
    assert bundle.items[0].sha256 == sha256(text.encode("utf-8")).hexdigest()
    assert bundle.total_bytes == len(text.encode("utf-8"))
    message = build_text_rubric_message(
        requirement_slug="reflection",
        requirement_name="Reflection",
        deterministic_result=ValidationResult(is_valid=True, message="Gate passed"),
        task=task,
        evidence=bundle.model_dump(mode="json"),
    )
    assert (
        json.loads(message.split("\n\n", 1)[1])["evidence"]["items"][0]["content"]
        == text
    )
    with pytest.raises(EvidenceError, match="evidence.item_limit"):
        apply_evidence_cap(task, [("career-reflection.md", text + "é")])


@pytest.mark.parametrize(
    "updates",
    [
        {"max_files": 0},
        {"max_file_size_bytes": -1},
        {"max_total_bytes": 0},
        {"required_files": ["career-reflection.md", "career-reflection.md"]},
        {"optional_files": ["career-reflection.md"]},
        {"required_files": ["../secret"]},
    ],
)
def test_invalid_configuration_is_not_a_learner_failure(updates):
    task = _with_policy(CAREER_REFLECTION_RUBRIC_TASK, **updates)
    with pytest.raises(EvidenceError, match="evidence.configuration") as caught:
        apply_evidence_cap(task, [("career-reflection.md", "text")])
    assert not caught.value.to_validation_result().verification_completed


@pytest.mark.parametrize(
    "tamper",
    [
        "truncated",
        "hash",
        "content",
        "total",
        "task",
        "source",
        "missing",
        "duplicate",
        "selection",
        "extra",
        "optional_presence",
    ],
)
def test_restored_tampered_packet_is_rejected_at_prompt_construction(tamper):
    task = SECURITY_SCANNING_RUBRIC_TASK
    bundle = apply_evidence_cap(
        task,
        [
            (task.evidence.required_files[0], "CodeQL"),
            (task.evidence.optional_files[0], "version: 2"),
        ],
    )
    data = bundle.model_dump(mode="json")
    if tamper == "truncated":
        data["items"][0]["truncated"] = True
    elif tamper == "hash":
        data["items"][0]["sha256"] = "wrong"
    elif tamper == "content":
        data["items"][0]["content"] = "codeql"
        assert (
            sum(len(item["content"].encode("utf-8")) for item in data["items"])
            == data["total_bytes"]
        )
    elif tamper == "total":
        data["total_bytes"] += 1
    elif tamper == "task":
        data["task_id"] = "wrong"
    elif tamper == "source":
        data["source"] = "submitted_text"
    elif tamper == "missing":
        data["items"].pop()
    elif tamper == "duplicate":
        data["items"].append(data["items"][0])
    elif tamper == "selection":
        data["selected_paths"] = []
    elif tamper == "extra":
        data["items"][0]["path"] = "outside.txt"
    else:
        data["optional_presence"] = {}
    restored = EvidenceBundle.model_validate(data)
    with pytest.raises(EvidenceError, match="evidence.selection"):
        build_repo_rubric_message(
            requirement_slug="security",
            requirement_name="Security",
            deterministic_result=ValidationResult(is_valid=True, message="Passed"),
            owner="owner",
            repo="repo",
            task=task,
            evidence=restored.model_dump(mode="json"),
        )


@pytest.mark.parametrize(
    "mutation", ["none", "truncated", "total", "refs", "gate", "malformed"]
)
def test_actual_serialized_request_is_revalidated_before_provider(mutation):
    task = CAREER_REFLECTION_RUBRIC_TASK
    bundle = apply_evidence_cap(
        task, [("career-reflection.md", "My complete 🦊 reflection")]
    )
    message = build_text_rubric_message(
        requirement_slug="reflection",
        requirement_name="Reflection",
        deterministic_result=ValidationResult(is_valid=True, message="Passed"),
        task=task,
        evidence=bundle.model_dump(mode="json"),
    )
    prefix, encoded = message.split("\n\n", 1)
    payload = json.loads(encoded)
    refs = ["career-reflection.md"]
    if mutation == "truncated":
        payload["evidence"]["items"][0]["truncated"] = True
    elif mutation == "total":
        payload["evidence"]["total_bytes"] = 0
    elif mutation == "refs":
        refs = ["invented.md"]
    elif mutation == "gate":
        payload["deterministic_result"]["is_valid"] = False
    request = LLMGradingRequest(
        task=task,
        allowed_evidence_refs=refs,
        message="malformed"
        if mutation == "malformed"
        else prefix + "\n\n" + json.dumps(payload),
    )
    if mutation == "none":
        validate_grading_request(request)
    else:
        with pytest.raises(EvidenceError, match="evidence.selection"):
            validate_grading_request(request)


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("max_file_size_bytes", 3, "evidence.item_limit"),
        ("max_total_bytes", 8, "evidence.total_limit"),
        ("max_files", 1, "evidence.file_limit"),
    ],
)
def test_prompt_boundary_recomputes_all_budget_limits(field, value, code):
    task = SECURITY_SCANNING_RUBRIC_TASK
    bundle = apply_evidence_cap(
        task,
        [
            (task.evidence.required_files[0], "CodeQL"),
            (task.evidence.optional_files[0], "version: 2"),
        ],
    )
    limited_task = _with_policy(task, **{field: value})
    with pytest.raises(EvidenceError, match=code):
        build_repo_rubric_message(
            requirement_slug="security",
            requirement_name="Security",
            deterministic_result=ValidationResult(is_valid=True, message="Passed"),
            owner="owner",
            repo="repo",
            task=limited_task,
            evidence=bundle.model_dump(mode="json"),
        )


@pytest.mark.parametrize(
    ("text", "oversized"),
    [
        ("abcd", False),
        ("éé", False),
        ("🦊", False),
        ("abcde", True),
        ("ééé", True),
        ("🦊a", True),
    ],
    ids=[
        "ascii-boundary",
        "two-byte-boundary",
        "four-byte-boundary",
        "ascii-oversized",
        "two-byte-oversized",
        "four-byte-oversized",
    ],
)
def test_restored_prompt_enforces_utf8_item_budget(text, oversized):
    task = CAREER_REFLECTION_RUBRIC_TASK
    bundle = apply_evidence_cap(task, [("career-reflection.md", text)])
    restored = EvidenceBundle.model_validate(bundle.model_dump(mode="json"))
    limited_task = _with_policy(task, max_file_size_bytes=4)
    assert restored.items[0].sha256 == sha256(text.encode("utf-8")).hexdigest()
    assert restored.total_bytes == len(text.encode("utf-8"))
    assert restored.total_bytes < limited_task.evidence.max_total_bytes
    kwargs = {
        "requirement_slug": "reflection",
        "requirement_name": "Reflection",
        "deterministic_result": ValidationResult(is_valid=True, message="Passed"),
        "task": limited_task,
        "evidence": restored.model_dump(mode="json"),
    }

    if oversized:
        with pytest.raises(EvidenceError, match="evidence.item_limit"):
            build_text_rubric_message(**kwargs)
    else:
        message = build_text_rubric_message(**kwargs)
        assert json.loads(message.split("\n\n", 1)[1])["evidence"] == kwargs["evidence"]


@pytest.mark.parametrize("field", ["selected_paths", "optional_presence"])
def test_evidence_packet_requires_current_selection_fields(field):
    task = SECURITY_SCANNING_RUBRIC_TASK
    bundle = apply_evidence_cap(task, [(task.evidence.required_files[0], "CodeQL")])
    data = bundle.model_dump(mode="json")
    del data[field]
    with pytest.raises(ValidationError):
        EvidenceBundle.model_validate(data)


async def test_wrong_source_is_configuration_failure_before_repository_access():
    repo = InMemoryRepoFiles({"career-reflection.md": "text"})
    with pytest.raises(EvidenceError, match="evidence.configuration"):
        await collect_repo_file_evidence(
            repo,
            "owner",
            "repo",
            [],
            CAREER_REFLECTION_RUBRIC_TASK,
        )
    assert not repo.file_reads


@pytest.mark.parametrize("boundary", ["tree", "collector"])
async def test_truncated_github_tree_is_never_trusted(monkeypatch, boundary):
    monkeypatch.setattr(
        repo_files_module,
        "github_api_get",
        AsyncMock(
            return_value=httpx.Response(
                200,
                json={
                    "truncated": True,
                    "tree": [{"type": "blob", "path": "Dockerfile"}],
                },
            )
        ),
    )
    repo = GitHubRepoFiles()
    with pytest.raises(EvidenceError, match="evidence.selection") as caught:
        if boundary == "tree":
            await repo.tree("owner", "repo")
        else:
            await collect_repo_file_evidence(
                repo, "owner", "repo", [], SECURITY_SCANNING_RUBRIC_TASK
            )
    result = caught.value.to_validation_result()
    assert not result.verification_completed
    assert not result.is_valid
    assert result.error_code == "evidence.selection"


@pytest.mark.parametrize(
    "reason", sorted(EVIDENCE_ERROR_CODES | {"complete", "retrieval"})
)
def test_evidence_event_has_closed_privacy_safe_attribute_contract(monkeypatch, reason):
    span = Mock()
    monkeypatch.setattr(evidence_module.trace, "get_current_span", lambda: span)
    evidence_module.record_evidence_decision(
        reason,
        selected_count=3,
        collected_count=2,
        total_bytes=123,
    )
    span.add_event.assert_called_once()
    name, attributes = span.add_event.call_args.args
    assert name == "verification.evidence.assembled"
    assert set(attributes) == {
        "evidence.outcome",
        "evidence.reason",
        "evidence.selected_count",
        "evidence.collected_count",
        "evidence.total_bytes",
    }
    assert attributes["evidence.outcome"] in {
        "complete",
        "required_missing",
        "retrieval_failed",
        "incomplete",
    }
    assert attributes["evidence.reason"] == reason
    assert attributes["evidence.selected_count"] == 3
    assert attributes["evidence.collected_count"] == 2
    assert attributes["evidence.total_bytes"] == 123


async def test_collection_telemetry_never_contains_sensitive_sentinels(monkeypatch):
    span = Mock()
    monkeypatch.setattr(evidence_module.trace, "get_current_span", lambda: span)
    secret_path = "SENTINEL-PATH.txt"
    content = "SENTINEL-CODE https://private.example/repo learner-secret"
    task = _with_policy(
        SECURITY_SCANNING_RUBRIC_TASK,
        required_files=[secret_path],
        optional_files=[],
    )
    await collect_repo_file_evidence(
        InMemoryRepoFiles({secret_path: content}),
        "private-owner",
        "private-repo",
        [secret_path],
        task,
    )
    span.add_event.assert_called_once()
    output = repr(span.add_event.call_args)
    assert all(
        secret not in output
        for secret in [
            secret_path,
            content,
            "private-owner",
            "private-repo",
            sha256(content.encode()).hexdigest(),
        ]
    )
