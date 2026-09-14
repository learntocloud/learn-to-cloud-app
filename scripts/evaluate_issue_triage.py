"""Export a blind triage prompt or score a saved JSON response without GitHub writes."""

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "scripts" / "issue_triage" / "cases.json"
WORKFLOW = ROOT / ".github" / "workflows" / "issue-triage.md"


def build_prompt(cases: list[dict], workflow: str) -> str:
    policy = workflow.split("\n---\n", 1)[1]
    inputs = [
        {key: value for key, value in case.items() if key != "expect"} for case in cases
    ]
    return (
        "Evaluate this triage policy against the supplied independent snapshots. "
        "Do not use tools, browse, edit files, or call GitHub. Snapshots replace "
        "all issue reads; omitted existing metadata is empty and there are no pending "
        "suggestions. Do not infer outcomes from source issue numbers. "
        "These are curated excerpts, not full original issue histories.\n\n"
        f"{policy}\n\n"
        "Return ONLY one JSON array, one object per input, with exactly these keys: "
        "id, issue_type, priority, labels. issue_type and priority are null "
        "(no change) "
        "or objects with value, rationale, confidence, and optional suggest:true. "
        "labels is an array of those same change objects. Each change needs its own "
        "rationale and confidence. Do not use Markdown fences.\n\n"
        f"SNAPSHOTS:\n{json.dumps(inputs, indent=2)}"
    )


def change_value(change: object) -> str | None:
    if change is None:
        return None
    if not isinstance(change, dict):
        raise ValueError("Changes must be objects or null.")
    if set(change) - {"value", "rationale", "confidence", "suggest"}:
        raise ValueError("Change contains an unsupported operation.")
    value = change.get("value")
    rationale = change.get("rationale")
    if not isinstance(value, str) or not value:
        raise ValueError("Change values must be nonempty strings.")
    if not isinstance(rationale, str) or not 1 <= len(rationale.strip()) <= 280:
        raise ValueError("Every change needs a rationale of 1-280 characters.")
    if change.get("confidence") not in ("LOW", "MEDIUM", "HIGH"):
        raise ValueError("Every change needs LOW, MEDIUM, or HIGH confidence.")
    if "suggest" in change and change["suggest"] is not True:
        raise ValueError("Changes must not explicitly request direct application.")
    return value


def score(cases: list[dict], response: object) -> list[str]:
    if not isinstance(response, list):
        raise ValueError("The response must be a JSON array.")
    by_id = {}
    for result in response:
        if not isinstance(result, dict) or set(result) != {
            "id",
            "issue_type",
            "priority",
            "labels",
        }:
            raise ValueError(
                "Each result needs exactly id, issue_type, priority, labels."
            )
        case_id = result["id"]
        if not isinstance(case_id, str) or case_id in by_id:
            raise ValueError("Result IDs must be unique strings.")
        by_id[case_id] = result
    if set(by_id) != {case["id"] for case in cases}:
        raise ValueError("Results must cover every case exactly once, with no extras.")
    failures = []
    for case in cases:
        result = by_id[case["id"]]
        expected = case["expect"]
        issue_type = change_value(result["issue_type"])
        priority = change_value(result["priority"])
        if not isinstance(result["labels"], list) or len(result["labels"]) > 3:
            raise ValueError("Each result permits at most three label changes.")
        labels = [change_value(label) for label in result["labels"]]
        if None in labels or len(set(labels)) != len(labels):
            raise ValueError("Label changes must be non-null and unique.")
        actual_labels = set(labels)
        if (
            issue_type not in expected["types"]
            or priority not in expected["priorities"]
            or not set(expected["required_labels"]) <= actual_labels
            or not actual_labels <= set(expected["allowed_labels"])
        ):
            failures.append(
                f"{case['id']}: type={issue_type}, priority={priority}, labels={labels}"
            )
    return failures


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--prompt", action="store_true", help="Print the blind evaluation prompt"
    )
    mode.add_argument("--score", type=Path, help="Score a saved JSON response")
    args = parser.parse_args()
    cases = json.loads(CASES.read_text())
    if args.prompt:
        print(build_prompt(cases, WORKFLOW.read_text()))
        return
    failures = score(cases, json.loads(args.score.read_text()))
    print(
        f"{len(cases) - len(failures)}/{len(cases)} cases within reviewed expectations"
    )
    for failure in failures:
        print(f"FAIL {failure}")
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
