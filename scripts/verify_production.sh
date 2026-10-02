#!/usr/bin/env bash
# Verify the production API revision is healthy, ready, and can submit verifications.
#
# Required env: APP_NAME, RESOURCE_GROUP, API_URL, SMOKE_SCOPE.
# Optional env: EXPECTED_IMAGE waits for the revision running that image;
# otherwise the latest revision is verified.
set -euo pipefail

: "${APP_NAME:?}" "${RESOURCE_GROUP:?}" "${API_URL:?}" "${SMOKE_SCOPE:?}"
EXPECTED_IMAGE=${EXPECTED_IMAGE:-}

show_logs() {
  az containerapp logs show \
    --name "$APP_NAME" --resource-group "$RESOURCE_GROUP" --revision "$1" \
    --tail 100 --format text 2>&1 || true
}

revision=""
if [[ -n "$EXPECTED_IMAGE" ]]; then
  echo "Looking for revision running image: $EXPECTED_IMAGE"
  for _ in {1..12}; do
    revision=$(az containerapp revision list \
      --name "$APP_NAME" --resource-group "$RESOURCE_GROUP" \
      --query "[?properties.template.containers[0].image=='$EXPECTED_IMAGE'] | [0].name" \
      -o tsv 2>/dev/null || true)
    if [[ -n "$revision" && "$revision" != "None" ]]; then
      break
    fi
    sleep 5
  done
else
  revision=$(az containerapp show \
    --name "$APP_NAME" --resource-group "$RESOURCE_GROUP" \
    --query properties.latestRevisionName --output tsv)
fi

if [[ -z "$revision" || "$revision" == "None" ]]; then
  echo "::error::No expected Container App revision was found." >&2
  exit 1
fi

ready=false
for i in {1..36}; do
  state=$(az containerapp revision show \
    --name "$APP_NAME" --resource-group "$RESOURCE_GROUP" --revision "$revision" \
    --query "{health:properties.healthState, running:properties.runningState, traffic:properties.trafficWeight}" \
    -o json 2>/dev/null || echo '{}')
  health=$(jq -r '.health // "Unknown"' <<<"$state")
  running=$(jq -r '.running // "Unknown"' <<<"$state")
  traffic=$(jq -r '.traffic // 0' <<<"$state")
  echo "Attempt $i: revision=$revision health=$health running=$running traffic=$traffic"

  if [[ "$running" =~ ^(ActivationFailed|Failed)$ ]]; then
    show_logs "$revision"
    exit 1
  fi
  if [[ "$health" == "Healthy" && "$traffic" -gt 0 ]]; then
    code=$(curl -s -o /dev/null -w "%{http_code}" "$API_URL/ready" || true)
    if [[ "$code" == "200" ]]; then
      ready=true
      break
    fi
  fi
  sleep 10
done

if [[ "$ready" != "true" ]]; then
  show_logs "$revision"
  exit 1
fi

access_token=$(az account get-access-token \
  --scope "$SMOKE_SCOPE" --query accessToken --output tsv)
echo "::add-mask::$access_token"

body=$(mktemp)
trap 'rm -f "$body"' EXIT
for i in {1..6}; do
  if ! code=$(curl --silent --output "$body" --write-out "%{http_code}" \
    --request POST "$API_URL/internal/smoke/verification" \
    --header "Authorization: Bearer $access_token"); then
    code=000
  fi
  echo "Smoke attempt $i: HTTP $code"
  if [[ "$code" == "200" ]]; then
    cat "$body"
    exit 0
  fi
  sleep 10
done

cat "$body" || true
exit 1
