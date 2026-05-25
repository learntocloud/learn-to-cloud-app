#!/usr/bin/env bash
set -euo pipefail

registry_name="${1:-}"
registry_endpoint="${2:-}"

if [[ -z "$registry_name" || -z "$registry_endpoint" ]]; then
  echo "Usage: $0 <acr-name> <acr-endpoint>" >&2
  exit 2
fi

missing=0

emit_error() {
  local message="$1"
  if [[ "${GITHUB_ACTIONS:-}" == "true" ]]; then
    echo "::error::$message"
    return
  fi

  echo "ERROR: $message" >&2
}

check_image() {
  local repository="$1"
  local tag="$2"
  local image_ref="$registry_endpoint/$repository:$tag"

  if az acr repository show-tags \
    --name "$registry_name" \
    --repository "$repository" \
    --query "contains(@, '$tag')" \
    --output tsv 2>/dev/null | grep -q true; then
    echo "Found required bootstrap image: $image_ref"
    return
  fi

  emit_error "Missing required bootstrap image: $image_ref"
  missing=1
}

check_image migrations bootstrap

if [[ "$missing" -eq 0 ]]; then
  exit 0
fi

cat <<EOF
Terraform uses bootstrap image tags to create Azure Container App resources.
Seed missing bootstrap images before terraform apply, for example:

  az acr login --name $registry_name
  docker build -f api/Dockerfile \\
    --target migrations-runtime \\
    -t $registry_endpoint/migrations:bootstrap .
  docker push $registry_endpoint/migrations:bootstrap
EOF

exit 1
