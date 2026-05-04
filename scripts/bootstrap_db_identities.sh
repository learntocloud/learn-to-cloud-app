#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Bootstrap database identities for PostgreSQL Entra least privilege.

This script creates or reuses:
  - A PostgreSQL Entra admin group
  - A migration app/service principal with GitHub Actions OIDC

It also sets the GitHub repository variables/secrets used by deploy.yml.

By default it creates/reuses identities and sets GitHub repository settings.
For production rollout, let GitHub Actions apply Terraform with repository
secrets, then run:

  scripts/bootstrap_db_identities.sh --skip-gh --run-sql

Only use --apply-terraform when you have the real production TF_VAR_* secrets
available locally.

Required tools:
  az, gh, terraform, psql

Environment overrides:
  ENVIRONMENT                         default: dev
  AZURE_SUBSCRIPTION_ID               default: current az account
  AZURE_TENANT_ID                     default: current az account tenant
  RESOURCE_GROUP                      default: rg-ltc-$ENVIRONMENT
  API_IDENTITY_NAME                   default: id-ltc-api-$ENVIRONMENT
  POSTGRES_DATABASE                   default: learntocloud
  POSTGRES_ADMIN_GROUP_NAME           default: Learn to Cloud PostgreSQL Admins
  MIGRATION_APP_NAME                  default: ltc-postgres-migrations-$ENVIRONMENT
  POSTGRES_MIGRATION_USER             default: $MIGRATION_APP_NAME
  GITHUB_REPO                         default: gh repo view --json nameWithOwner
  GITHUB_OIDC_REF                     default: refs/heads/main
  FEDERATED_CREDENTIAL_NAME           default: github-actions-$ENVIRONMENT-main
  POSTGRES_HOST                       default: terraform output database_host
  TERRAFORM_VAR_FILE                  default: infra/terraform.tfvars.local when present

Options:
  --apply-terraform                   run terraform init/validate/plan/apply
  --run-sql                           run infra/postgres-bootstrap.sql
  --skip-gh                           do not set GitHub repo variables/secrets
  --help                              show this help
EOF
}

log() {
  printf '\n==> %s\n' "$*" >&2
}

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "Required command not found: $1"
}

slugify() {
  printf '%s' "$1" |
    tr '[:upper:]' '[:lower:]' |
    tr -cs '[:alnum:]' '-' |
    sed -e 's/^-//' -e 's/-$//' |
    cut -c1-60
}

create_or_get_group() {
  local group_name="$1"
  local group_id

  group_id="$(
    az ad group list \
      --display-name "$group_name" \
      --query '[0].id' \
      -o tsv
  )"

  if [[ -n "$group_id" ]]; then
    log "Using existing Entra group: $group_name ($group_id)"
  else
    local mail_nickname
    mail_nickname="$(slugify "$group_name")"
    log "Creating Entra group: $group_name"
    group_id="$(
      az ad group create \
        --display-name "$group_name" \
        --mail-nickname "$mail_nickname" \
        --query id \
        -o tsv
    )"
  fi

  printf '%s' "$group_id"
}

add_current_user_to_group_if_possible() {
  local group_id="$1"
  local user_id

  user_id="$(
    az ad signed-in-user show --query id -o tsv 2>/dev/null || true
  )"

  if [[ -z "$user_id" ]]; then
    log "Current az login is not a user; skipping admin group membership check"
    return
  fi

  local is_member
  is_member="$(
    az ad group member check \
      --group "$group_id" \
      --member-id "$user_id" \
      --query value \
      -o tsv
  )"

  if [[ "$is_member" == "true" ]]; then
    log "Current user is already a member of the PostgreSQL admin group"
    return
  fi

  log "Adding current user to PostgreSQL admin group"
  az ad group member add --group "$group_id" --member-id "$user_id"
  log "If PostgreSQL group login fails, run az login again after membership propagates"
}

create_or_get_migration_app() {
  local app_name="$1"
  local app_id

  app_id="$(
    az ad app list \
      --display-name "$app_name" \
      --query '[0].appId' \
      -o tsv
  )"

  if [[ -n "$app_id" ]]; then
    log "Using existing migration app registration: $app_name ($app_id)"
  else
    log "Creating migration app registration: $app_name"
    app_id="$(
      az ad app create \
        --display-name "$app_name" \
        --query appId \
        -o tsv
    )"
  fi

  printf '%s' "$app_id"
}

create_or_get_service_principal() {
  local app_id="$1"
  local sp_object_id

  sp_object_id="$(
    az ad sp list \
      --filter "appId eq '$app_id'" \
      --query '[0].id' \
      -o tsv
  )"

  if [[ -n "$sp_object_id" ]]; then
    log "Using existing migration service principal: $sp_object_id"
  else
    log "Creating migration service principal"
    sp_object_id="$(
      az ad sp create \
        --id "$app_id" \
        --query id \
        -o tsv
    )"
  fi

  printf '%s' "$sp_object_id"
}

ensure_federated_credential() {
  local app_id="$1"
  local credential_name="$2"
  local github_repo="$3"
  local github_ref="$4"
  local existing

  existing="$(
    az ad app federated-credential list \
      --id "$app_id" \
      --query "[?name=='$credential_name'].name | [0]" \
      -o tsv
  )"

  if [[ -n "$existing" ]]; then
    log "Using existing federated credential: $credential_name"
    return
  fi

  local credential_file
  credential_file="$(mktemp)"

  printf '%s\n' \
    '{' \
    "  \"name\": \"$credential_name\"," \
    "  \"issuer\": \"https://token.actions.githubusercontent.com\"," \
    "  \"subject\": \"repo:$github_repo:ref:$github_ref\"," \
    "  \"description\": \"GitHub Actions migrations for $github_repo $github_ref\"," \
    '  "audiences": ["api://AzureADTokenExchange"]' \
    '}' >"$credential_file"

  log "Creating federated credential for GitHub OIDC: repo:$github_repo:ref:$github_ref"
  az ad app federated-credential create \
    --id "$app_id" \
    --parameters "$credential_file" \
    >/dev/null
  rm -f "$credential_file"
}

set_github_settings() {
  local repo="$1"
  local admin_group_id="$2"
  local admin_group_name="$3"
  local migration_user="$4"
  local migration_client_id="$5"

  log "Setting GitHub repository variables/secrets on $repo"
  gh variable set POSTGRES_ENTRA_ADMIN_OBJECT_ID \
    --repo "$repo" \
    --body "$admin_group_id"
  gh variable set POSTGRES_ENTRA_ADMIN_PRINCIPAL_NAME \
    --repo "$repo" \
    --body "$admin_group_name"
  gh variable set POSTGRES_ENTRA_ADMIN_PRINCIPAL_TYPE \
    --repo "$repo" \
    --body "Group"
  gh variable set POSTGRES_MIGRATION_USER \
    --repo "$repo" \
    --body "$migration_user"
  gh variable set DB_IDENTITY_BOOTSTRAPPED \
    --repo "$repo" \
    --body "false"
  gh secret set AZURE_MIGRATION_CLIENT_ID \
    --repo "$repo" \
    --body "$migration_client_id"
}

mark_bootstrapped() {
  local repo="$1"

  log "Marking database identity bootstrap complete for $repo"
  gh variable set DB_IDENTITY_BOOTSTRAPPED \
    --repo "$repo" \
    --body "true"
}

apply_terraform() {
  local repo_root="$1"
  local subscription_id="$2"
  local admin_group_id="$3"
  local admin_group_name="$4"

  log "Applying Terraform with PostgreSQL admin group variables"
  export TF_VAR_subscription_id="$subscription_id"
  export TF_VAR_postgres_entra_admin_object_id="$admin_group_id"
  export TF_VAR_postgres_entra_admin_principal_name="$admin_group_name"
  export TF_VAR_postgres_entra_admin_principal_type="Group"

  local -a var_file_args=()
  local var_file="${TERRAFORM_VAR_FILE:-}"
  if [[ -z "$var_file" && -f "$repo_root/infra/terraform.tfvars.local" ]]; then
    var_file="$repo_root/infra/terraform.tfvars.local"
  fi
  if [[ -n "$var_file" ]]; then
    [[ -f "$var_file" ]] || die "TERRAFORM_VAR_FILE does not exist: $var_file"
    log "Using Terraform variable file: $var_file"
    var_file_args=(-var-file="$var_file")
  fi

  terraform -chdir="$repo_root/infra" init
  terraform -chdir="$repo_root/infra" validate
  terraform -chdir="$repo_root/infra" plan \
    "${var_file_args[@]}" \
    -out=tfplan \
    -input=false \
    -lock-timeout=120s
  terraform -chdir="$repo_root/infra" apply \
    "${var_file_args[@]}" \
    -auto-approve \
    -lock-timeout=120s \
    tfplan
}

terraform_output_or_empty() {
  local repo_root="$1"
  local output_name="$2"

  terraform -chdir="$repo_root/infra" output -raw "$output_name" 2>/dev/null || true
}

tfvar_file_has_key() {
  local key="$1"
  local file

  for file in "$REPO_ROOT/infra/terraform.tfvars" "$REPO_ROOT/infra/terraform.tfvars.local"; do
    [[ -f "$file" ]] || continue
    grep -Eq "^[[:space:]]*$key[[:space:]]*=" "$file"
  done
}

tfvar_is_available() {
  local key="$1"
  local env_name="TF_VAR_$key"

  [[ -n "${!env_name:-}" ]] || tfvar_file_has_key "$key"
}

check_required_terraform_vars() {
  local required=(
    github_client_id
    github_client_secret
    github_token
    session_secret_key
    labs_verification_secret
  )
  local missing=()
  local key

  for key in "${required[@]}"; do
    if ! tfvar_is_available "$key"; then
      missing+=("$key")
    fi
  done

  if [[ "${#missing[@]}" -gt 0 ]]; then
    printf 'Missing Terraform variables required for local apply:\n' >&2
    printf '  - %s\n' "${missing[@]}" >&2
    cat >&2 <<'EOF'

Provide them as TF_VAR_* environment variables or in infra/terraform.tfvars.local.
Do not use placeholders: these values feed production Container App secrets.
EOF
    exit 1
  fi
}

run_postgres_bootstrap() {
  local repo_root="$1"
  local resource_group="$2"
  local api_identity_name="$3"
  local postgres_host="$4"
  local postgres_database="$5"
  local admin_group_name="$6"
  local migration_user="$7"
  local migration_object_id="$8"

  local api_object_id
  api_object_id="$(
    az identity show \
      --resource-group "$resource_group" \
      --name "$api_identity_name" \
      --query principalId \
      -o tsv
  )"

  [[ -n "$api_object_id" ]] || die "Could not resolve API identity principal ID"
  [[ -n "$postgres_host" ]] || die "POSTGRES_HOST is required to run SQL bootstrap"

  log "Running PostgreSQL bootstrap SQL"
  PGPASSWORD="$(
    az account get-access-token \
      --resource-type oss-rdbms \
      --query accessToken \
      -o tsv
  )" \
  PGHOST="$postgres_host" \
  PGDATABASE="postgres" \
  PGUSER="$admin_group_name" \
  PGSSLMODE="require" \
  psql \
    -v database_name="$postgres_database" \
    -v api_role="$api_identity_name" \
    -v api_object_id="$api_object_id" \
    -v migration_role="$migration_user" \
    -v migration_object_id="$migration_object_id" \
    -f "$repo_root/infra/postgres-bootstrap.sql"
}

APPLY_TERRAFORM=false
RUN_SQL=false
SET_GH=true

while [[ $# -gt 0 ]]; do
  case "$1" in
    --apply-terraform)
      APPLY_TERRAFORM=true
      shift
      ;;
    --run-sql)
      RUN_SQL=true
      shift
      ;;
    --skip-gh)
      SET_GH=false
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      die "Unknown argument: $1"
      ;;
  esac
done

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

require_cmd az
require_cmd gh
require_cmd terraform
require_cmd psql

ENVIRONMENT="${ENVIRONMENT:-dev}"
AZURE_SUBSCRIPTION_ID="${AZURE_SUBSCRIPTION_ID:-$(az account show --query id -o tsv)}"
AZURE_TENANT_ID="${AZURE_TENANT_ID:-$(az account show --query tenantId -o tsv)}"
RESOURCE_GROUP="${RESOURCE_GROUP:-rg-ltc-$ENVIRONMENT}"
API_IDENTITY_NAME="${API_IDENTITY_NAME:-id-ltc-api-$ENVIRONMENT}"
POSTGRES_DATABASE="${POSTGRES_DATABASE:-learntocloud}"
POSTGRES_ADMIN_GROUP_NAME="${POSTGRES_ADMIN_GROUP_NAME:-Learn to Cloud PostgreSQL Admins}"
MIGRATION_APP_NAME="${MIGRATION_APP_NAME:-ltc-postgres-migrations-$ENVIRONMENT}"
POSTGRES_MIGRATION_USER="${POSTGRES_MIGRATION_USER:-$MIGRATION_APP_NAME}"
GITHUB_REPO="${GITHUB_REPO:-$(gh repo view --json nameWithOwner --jq .nameWithOwner)}"
GITHUB_OIDC_REF="${GITHUB_OIDC_REF:-refs/heads/main}"
FEDERATED_CREDENTIAL_NAME="${FEDERATED_CREDENTIAL_NAME:-github-actions-$ENVIRONMENT-main}"

log "Using subscription $AZURE_SUBSCRIPTION_ID in tenant $AZURE_TENANT_ID"
az account set --subscription "$AZURE_SUBSCRIPTION_ID"

ADMIN_GROUP_ID="$(create_or_get_group "$POSTGRES_ADMIN_GROUP_NAME")"
add_current_user_to_group_if_possible "$ADMIN_GROUP_ID"

MIGRATION_CLIENT_ID="$(create_or_get_migration_app "$MIGRATION_APP_NAME")"
MIGRATION_OBJECT_ID="$(create_or_get_service_principal "$MIGRATION_CLIENT_ID")"
ensure_federated_credential \
  "$MIGRATION_CLIENT_ID" \
  "$FEDERATED_CREDENTIAL_NAME" \
  "$GITHUB_REPO" \
  "$GITHUB_OIDC_REF"

if [[ "$SET_GH" == "true" ]]; then
  set_github_settings \
    "$GITHUB_REPO" \
    "$ADMIN_GROUP_ID" \
    "$POSTGRES_ADMIN_GROUP_NAME" \
    "$POSTGRES_MIGRATION_USER" \
    "$MIGRATION_CLIENT_ID"
fi

if [[ "$APPLY_TERRAFORM" == "true" ]]; then
  check_required_terraform_vars
  apply_terraform \
    "$REPO_ROOT" \
    "$AZURE_SUBSCRIPTION_ID" \
    "$ADMIN_GROUP_ID" \
    "$POSTGRES_ADMIN_GROUP_NAME"
fi

if [[ "$RUN_SQL" == "true" ]]; then
  POSTGRES_HOST="${POSTGRES_HOST:-$(terraform_output_or_empty "$REPO_ROOT" database_host)}"
  run_postgres_bootstrap \
    "$REPO_ROOT" \
    "$RESOURCE_GROUP" \
    "$API_IDENTITY_NAME" \
    "$POSTGRES_HOST" \
    "$POSTGRES_DATABASE" \
    "$POSTGRES_ADMIN_GROUP_NAME" \
    "$POSTGRES_MIGRATION_USER" \
    "$MIGRATION_OBJECT_ID"
  mark_bootstrapped "$GITHUB_REPO"
fi

cat <<EOF

Bootstrap identity setup complete.

PostgreSQL admin group:
  name:      $POSTGRES_ADMIN_GROUP_NAME
  object ID: $ADMIN_GROUP_ID

Migration principal:
  app name:         $MIGRATION_APP_NAME
  client ID:        $MIGRATION_CLIENT_ID
  object ID:        $MIGRATION_OBJECT_ID
  PostgreSQL role:  $POSTGRES_MIGRATION_USER

GitHub repo:
  $GITHUB_REPO

Next steps:
  1. Merge the branch so GitHub Actions applies Terraform with repository secrets.
  2. Run scripts/bootstrap_db_identities.sh --skip-gh --run-sql after Terraform succeeds.
  3. Run the deploy workflow manually after DB_IDENTITY_BOOTSTRAPPED is true.
EOF
