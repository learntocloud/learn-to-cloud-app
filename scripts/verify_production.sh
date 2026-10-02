#!/usr/bin/env bash
# Verify the production API revision runs the expected image, is healthy, and is ready.
#
# Required env: APP_NAME, RESOURCE_GROUP, API_URL, EXPECTED_IMAGE.
# The app's latest revision must run EXPECTED_IMAGE; deploys are serialized, so
# any other image means something outside the deploy workflow changed the app.
set -euo pipefail

: "${APP_NAME:?}" "${RESOURCE_GROUP:?}" "${API_URL:?}"
: "${EXPECTED_IMAGE:?}"

show_logs() {
  az containerapp logs show \
    --name "$APP_NAME" --resource-group "$RESOURCE_GROUP" --revision "$1" \
    --tail 100 --format text 2>&1 || true
}

latest=$(az containerapp show \
  --name "$APP_NAME" --resource-group "$RESOURCE_GROUP" \
  --query "{revision: properties.latestRevisionName, image: properties.template.containers[?name=='api'] | [0].image}" \
  -o json)
revision=$(jq -r '.revision // empty' <<<"$latest")
image=$(jq -r '.image // empty' <<<"$latest")

if [[ -z "$revision" ]]; then
  echo "::error::The Container App has no latest revision." >&2
  exit 1
fi
if [[ "$image" != "$EXPECTED_IMAGE" ]]; then
  echo "::error::Latest revision $revision runs $image, expected $EXPECTED_IMAGE." >&2
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

echo "Revision $revision is healthy and ready."
