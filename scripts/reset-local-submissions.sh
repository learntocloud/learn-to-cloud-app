#!/usr/bin/env bash
#
# Preview and reset local verification attempts for every curriculum requirement.
#
# Usage:
#   scripts/reset-local-submissions.sh
#   scripts/reset-local-submissions.sh --user-id 12345
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
api_dir="$repo_root/api"
curriculum="$repo_root/packages/learn-to-cloud-shared/src/learn_to_cloud_shared/content/curriculum.json"

usage() {
    cat <<'EOF'
Usage: scripts/reset-local-submissions.sh [--user-id GITHUB_USER_ID]

Preview and delete all local verification attempts. Without --user-id, attempts
for every local user are included. Repeat --user-id to target multiple users.
EOF
}

user_args=()
while (($#)); do
    case "$1" in
        --user-id)
            if (($# < 2)) || [[ ! "$2" =~ ^[0-9]+$ ]]; then
                echo "Error: --user-id requires a numeric GitHub user ID." >&2
                exit 2
            fi
            user_args+=(--user-id "$2")
            shift 2
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "Error: unknown argument: $1" >&2
            usage >&2
            exit 2
            ;;
    esac
done

requirement_args=()
while IFS= read -r slug; do
    requirement_args+=(--requirement-slug "$slug")
done < <(
    uv run python -c '
import json
import sys

with open(sys.argv[1]) as curriculum_file:
    curriculum = json.load(curriculum_file)

for phase in curriculum["phases"]:
    verification = phase.get("hands_on_verification") or {}
    for slug in verification.get("requirement_slugs", []):
        print(slug)
' "$curriculum"
)

if ((${#requirement_args[@]} == 0)); then
    echo "Error: no verification requirements found in the curriculum." >&2
    exit 1
fi

cd "$api_dir"
uv run python scripts/reset_local_submissions.py \
    --dry-run \
    "${user_args[@]}" \
    "${requirement_args[@]}"

echo
read -r -p "Delete the verification attempts shown above? [y/N] " confirmation
case "$confirmation" in
    y|Y|yes|YES)
        uv run python scripts/reset_local_submissions.py \
            "${user_args[@]}" \
            "${requirement_args[@]}"
        ;;
    *)
        echo "Reset cancelled."
        ;;
esac
