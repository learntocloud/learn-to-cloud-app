#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -lt 2 ]; then
  echo "Usage: $0 GITHUB_OAUTH_CLIENT_ID REVIEWER_LOGIN..." >&2
  exit 2
fi

github_client_id=$1
shift
reviewer_logins=("$@")
repository=${REPOSITORY:-learntocloud/learn-to-cloud-app}
environment_name=${TERRAFORM_PLAN_ENVIRONMENT:-terraform-plan}
application_name=${TERRAFORM_PLAN_APPLICATION_NAME:-github-learntocloud-terraform-plan}
state_resource_group=${TF_STATE_RESOURCE_GROUP:-rg-terraform-state}
state_storage_account=${TF_STATE_STORAGE_ACCOUNT:-stterraformstateb1ac9ddc}
state_container=${TF_STATE_CONTAINER:-tfstate}
federated_credential_name=github-${environment_name}

for command in az gh jq; do
  if ! command -v "$command" >/dev/null 2>&1; then
    echo "Required command not found: $command" >&2
    exit 1
  fi
done

az account show >/dev/null
gh auth status >/dev/null

subscription_id=${AZURE_SUBSCRIPTION_ID:-$(az account show --query id -o tsv)}
tenant_id=$(az account show --query tenantId -o tsv)
subscription_scope="/subscriptions/$subscription_id"
container_scope="${subscription_scope}/resourceGroups/${state_resource_group}/providers/Microsoft.Storage/storageAccounts/${state_storage_account}/blobServices/default/containers/${state_container}"
oidc_subject="repo:${repository}:environment:${environment_name}"

repo_variable() {
  local name=$1
  local value

  if ! value=$(gh variable get "$name" --repo "$repository" --json value --jq .value 2>/dev/null); then
    echo "Repository variable $name is required before configuring the plan environment." >&2
    exit 1
  fi

  if [ -z "$value" ]; then
    echo "Repository variable $name must not be empty." >&2
    exit 1
  fi

  printf '%s' "$value"
}

app_matches=$(az ad app list --display-name "$application_name" --query "length(@)" -o tsv)
if [ "$app_matches" -gt 1 ]; then
  echo "Multiple Entra applications are named $application_name; resolve the duplicate before continuing." >&2
  exit 1
fi

if [ "$app_matches" -eq 0 ]; then
  app_id=$(az ad app create --display-name "$application_name" --sign-in-audience AzureADMyOrg --query appId -o tsv)
else
  app_id=$(az ad app list --display-name "$application_name" --query "[0].appId" -o tsv)
fi

if ! service_principal_id=$(az ad sp show --id "$app_id" --query id -o tsv 2>/dev/null); then
  az ad sp create --id "$app_id" --output none
  for _ in {1..12}; do
    if service_principal_id=$(az ad sp show --id "$app_id" --query id -o tsv 2>/dev/null); then
      break
    fi
    sleep 5
  done
fi

if [ -z "${service_principal_id:-}" ]; then
  echo "The Entra service principal was created but did not become readable in time." >&2
  exit 1
fi

credential=$(az ad app federated-credential list \
  --id "$app_id" \
  --query "[?name=='${federated_credential_name}'] | [0]" \
  -o json)

if [ -z "$(jq -r '.name // empty' <<< "$credential")" ]; then
  credential_parameters=$(jq -cn \
    --arg name "$federated_credential_name" \
    --arg subject "$oidc_subject" \
    '{
      name: $name,
      issuer: "https://token.actions.githubusercontent.com",
      subject: $subject,
      description: "Read-only Terraform plans approved through the GitHub environment",
      audiences: ["api://AzureADTokenExchange"]
    }')
  az ad app federated-credential create \
    --id "$app_id" \
    --parameters "$credential_parameters" \
    --output none
elif ! jq -e \
  --arg subject "$oidc_subject" \
  '.issuer == "https://token.actions.githubusercontent.com"
    and .subject == $subject
    and (.audiences == ["api://AzureADTokenExchange"])' <<< "$credential" >/dev/null; then
  echo "Federated credential $federated_credential_name exists with unexpected trust settings." >&2
  exit 1
fi

ensure_role_assignment() {
  local role=$1
  local scope=$2
  local assignment_count

  assignment_count=$(az role assignment list \
    --assignee-object-id "$service_principal_id" \
    --role "$role" \
    --scope "$scope" \
    --query "length(@)" \
    -o tsv)

  if [ "$assignment_count" -eq 0 ]; then
    az role assignment create \
      --assignee-object-id "$service_principal_id" \
      --assignee-principal-type ServicePrincipal \
      --role "$role" \
      --scope "$scope" \
      --output none
  fi
}

ensure_role_assignment Reader "$subscription_scope"
ensure_role_assignment "Storage Blob Data Reader" "$container_scope"

reviewers='[]'
for reviewer_login in "${reviewer_logins[@]}"; do
  reviewer_id=$(gh api "users/$reviewer_login" --jq .id)
  reviewers=$(jq -c \
    --argjson reviewer_id "$reviewer_id" \
    '. + [{type: "User", id: $reviewer_id}]' <<< "$reviewers")
done

environment_parameters=$(jq -cn \
  --argjson reviewers "$reviewers" \
  '{
    wait_timer: 0,
    prevent_self_review: true,
    reviewers: $reviewers,
    deployment_branch_policy: null
  }')
environment_file=$(mktemp)
trap 'rm -f "$environment_file"' EXIT
printf '%s' "$environment_parameters" > "$environment_file"
gh api \
  --method PUT \
  "repos/${repository}/environments/${environment_name}" \
  --input "$environment_file" \
  >/dev/null

environment_variables=(
  "AZURE_TERRAFORM_PLAN_CLIENT_ID=$app_id"
  "AZURE_TENANT_ID=$tenant_id"
  "AZURE_SUBSCRIPTION_ID=$subscription_id"
  "AZURE_ENV_NAME=$(repo_variable AZURE_ENV_NAME)"
  "AZURE_LOCATION=$(repo_variable AZURE_LOCATION)"
  "TERRAFORM_GITHUB_CLIENT_ID=$github_client_id"
  "POSTGRES_ENTRA_ADMIN_OBJECT_ID=$(repo_variable POSTGRES_ENTRA_ADMIN_OBJECT_ID)"
  "POSTGRES_ENTRA_ADMIN_PRINCIPAL_NAME=$(repo_variable POSTGRES_ENTRA_ADMIN_PRINCIPAL_NAME)"
  "POSTGRES_ENTRA_ADMIN_PRINCIPAL_TYPE=$(repo_variable POSTGRES_ENTRA_ADMIN_PRINCIPAL_TYPE)"
)

for variable in "${environment_variables[@]}"; do
  name=${variable%%=*}
  value=${variable#*=}
  gh variable set "$name" \
    --repo "$repository" \
    --env "$environment_name" \
    --body "$value"
done

cat <<EOF
Terraform plan access configured.

Entra application: $application_name
Client ID: $app_id
OIDC subject: $oidc_subject
Azure roles:
  Reader at $subscription_scope
  Storage Blob Data Reader at $container_scope

Add terraform-plan-status to the main branch ruleset's required status checks.
EOF
