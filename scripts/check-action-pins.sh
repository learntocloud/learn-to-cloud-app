#!/usr/bin/env bash
set -euo pipefail

declare -A checked
failed=false

while IFS=: read -r file line content; do
  reference=$(sed -E 's/^[[:space:]-]*uses:[[:space:]]*([^[:space:]#]+).*/\1/' <<< "$content")
  if [[ "$reference" == ./* || "$reference" == docker://* ]]; then
    continue
  fi

  action=${reference%@*}
  revision=${reference##*@}
  repository=$(cut -d/ -f1,2 <<< "$action")
  version=$(sed -nE 's/.*#[[:space:]]*(v[^[:space:]]+).*/\1/p' <<< "$content")

  if [[ ! "$revision" =~ ^[0-9a-f]{40}$ || -z "$version" ]]; then
    echo "::error file=$file,line=$line::External actions must use a full commit SHA and a version comment."
    failed=true
    continue
  fi

  key="$repository@$revision#$version"
  if [[ -n "${checked[$key]:-}" ]]; then
    continue
  fi
  checked[$key]=1

  if ! tag_refs=$(
    git ls-remote \
      "https://github.com/$repository.git" \
      "refs/tags/$version" \
      "refs/tags/$version^{}"
  ); then
    echo "::error file=$file,line=$line::Unable to resolve $repository tag $version."
    failed=true
    continue
  fi
  tag_revision=$(awk '$2 ~ /\^\{\}$/ {print $1}' <<< "$tag_refs")
  if [[ -z "$tag_revision" ]]; then
    tag_revision=$(awk 'NR == 1 {print $1}' <<< "$tag_refs")
  fi

  if [[ -z "$tag_revision" ]]; then
    echo "::error file=$file,line=$line::$repository does not have tag $version."
    failed=true
  elif [[ "$revision" != "$tag_revision" ]]; then
    echo "::error file=$file,line=$line::$repository $version resolves to $tag_revision, not $revision."
    failed=true
  fi
done < <(
  grep -RnE '^[[:space:]]*(-[[:space:]]*)?uses:' \
    --include='*.yml' \
    --include='*.yaml' \
    .github/workflows
)

if [[ "$failed" == "true" ]]; then
  exit 1
fi

echo "All external GitHub Actions pins match their version tags."
