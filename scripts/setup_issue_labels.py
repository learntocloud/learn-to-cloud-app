"""Preview or apply the repository's managed issue-label definitions."""

import argparse
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

DEFINITIONS = Path(__file__).parent / "issue_triage" / "labels.json"
DEFAULT_REPO = "learntocloud/learn-to-cloud-app"


@dataclass(frozen=True)
class Label:
    name: str
    color: str
    description: str


def parse_label(value: object) -> Label:
    if not isinstance(value, dict):
        raise ValueError("Each label must be an object.")
    name = value.get("name")
    color = value.get("color")
    description = value.get("description")
    if not isinstance(name, str) or not name.strip() or len(name) > 50:
        raise ValueError("Label names must contain 1-50 characters.")
    if not isinstance(color, str) or not re.fullmatch(r"[0-9a-fA-F]{6}", color):
        raise ValueError(f"Label {name!r} requires a six-digit hexadecimal color.")
    if not isinstance(description, str) or len(description) > 100:
        raise ValueError(
            f"Label {name!r} requires a description of at most 100 characters."
        )
    return Label(name, color.lower(), description)


def load_definitions(path: Path = DEFINITIONS) -> list[Label]:
    values = json.loads(path.read_text())
    if not isinstance(values, list) or not values:
        raise ValueError("Label definitions must be a nonempty array.")
    labels = [parse_label(value) for value in values]
    if any(not label.description.strip() for label in labels):
        raise ValueError("Managed labels require nonempty descriptions.")
    if len({label.name.casefold() for label in labels}) != len(labels):
        raise ValueError("Managed label names must be unique, ignoring case.")
    return labels


def github(args: list[str], payload: object = None) -> object:
    result = subprocess.run(
        ["gh", "api", "--hostname", "github.com", *args],
        input=json.dumps(payload) if payload is not None else None,
        text=True,
        capture_output=True,
        check=True,
    )
    return json.loads(result.stdout)


def existing_labels(repo: str) -> list[Label]:
    pages = github(["--paginate", "--slurp", f"repos/{repo}/labels?per_page=100"])
    if not isinstance(pages, list) or any(not isinstance(page, list) for page in pages):
        raise ValueError("GitHub returned an invalid paginated label response.")
    labels = []
    for page in pages:
        for value in page:
            if isinstance(value, dict) and value.get("description") is None:
                value = {**value, "description": ""}
            labels.append(parse_label(value))
    return labels


def plan_labels(desired: list[Label], existing: list[Label]) -> list[tuple[str, Label]]:
    by_name = {label.name.casefold(): label for label in existing}
    changes = []
    for label in desired:
        previous = by_name.get(label.name.casefold())
        if previous is None:
            changes.append(("create", label))
        elif (previous.color, previous.description) != (label.color, label.description):
            changes.append(("update", label))
    return changes


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=DEFAULT_REPO, help="GitHub owner/repository")
    parser.add_argument(
        "--apply", action="store_true", help="Apply the previewed label definitions"
    )
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", args.repo):
        parser.error("--repo must be an owner/repository on github.com")
    try:
        desired = load_definitions()
        changes = plan_labels(desired, existing_labels(args.repo))
        print(f"Repository: {args.repo}")
        for action, label in changes:
            print(f"{action.upper()} {label.name} #{label.color}: {label.description}")
        if not changes:
            print("All managed labels already match. No changes needed.")
        elif not args.apply:
            print("Preview only. Re-run with --apply to create/update these labels.")
        else:
            for action, label in changes:
                method = "POST" if action == "create" else "PATCH"
                path = f"repos/{args.repo}/labels"
                payload = {"color": label.color, "description": label.description}
                if action == "create":
                    payload["name"] = label.name
                else:
                    path += f"/{quote(label.name, safe='')}"
                github(["--method", method, path, "--input", "-"], payload)
            print(f"Applied {len(changes)} label changes. No labels or issues deleted.")
    except subprocess.CalledProcessError as error:
        parser.exit(1, f"GitHub command failed: {error.stderr or str(error)}\n")
    except (ValueError, OSError) as error:
        parser.exit(1, f"Label setup failed: {error}\n")


if __name__ == "__main__":
    main()
