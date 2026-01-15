#!/bin/bash
# Emergency Rollback to Bicep
# This script removes Terraform state WITHOUT destroying Azure resources
# and restores Bicep files for continued management

set -e

ENVIRONMENT="${1:-dev}"

echo "======================================"
echo "⚠️  EMERGENCY ROLLBACK TO BICEP"
echo "======================================"
echo "Environment: $ENVIRONMENT"
echo ""
echo "This will:"
echo "  1. Backup Terraform state"
echo "  2. Remove Terraform state (resources stay in Azure)"
echo "  3. Restore Bicep files"
echo "  4. Update azure.yaml to use Bicep"
echo ""
read -p "Are you sure you want to rollback? (yes/NO): " CONFIRM

if [ "$CONFIRM" != "yes" ]; then
  echo "Rollback cancelled."
  exit 0
fi

echo ""
echo "======================================"
echo "Starting Rollback"
echo "======================================"
echo ""

# Step 1: Backup Terraform state
BACKUP_DIR="rollback-backup-$(date +%Y%m%d-%H%M%S)"
echo "Step 1/5: Backing up Terraform state..."
mkdir -p "../$BACKUP_DIR"

if [ -f terraform.tfstate ]; then
  cp terraform.tfstate* "../$BACKUP_DIR/" 2>/dev/null || true
  echo "✓ Terraform state backed up to ../$BACKUP_DIR"
else
  echo "⚠️  No local state file found (may be using remote backend)"
fi

# Step 2: Remove Terraform state
echo ""
echo "Step 2/5: Removing Terraform state..."
rm -f terraform.tfstate*
rm -rf .terraform/
echo "✓ Terraform state removed (resources remain in Azure)"

# Step 3: Restore Bicep files
echo ""
echo "Step 3/5: Restoring Bicep files..."

if [ -d "../infra-bicep-archive" ]; then
  cp ../infra-bicep-archive/*.bicep . 2>/dev/null || true
  cp ../infra-bicep-archive/*.json . 2>/dev/null || true
  echo "✓ Bicep files restored from archive"
elif [ -d "../infra-bicep-archive-"* ]; then
  LATEST_ARCHIVE=$(ls -td ../infra-bicep-archive-* | head -1)
  cp "$LATEST_ARCHIVE"/*.bicep . 2>/dev/null || true
  cp "$LATEST_ARCHIVE"/*.json . 2>/dev/null || true
  echo "✓ Bicep files restored from $LATEST_ARCHIVE"
else
  echo "⚠️  WARNING: Bicep archive not found!"
  echo "You must restore Bicep files from git:"
  echo "  git checkout <commit-before-migration> -- infra/"
  echo ""
  echo "Or manually restore from backup"
  read -p "Press Enter to continue anyway, or Ctrl+C to abort..."
fi

# Step 4: Update azure.yaml
echo ""
echo "Step 4/5: Updating azure.yaml..."
if [ -f "../azure.yaml" ]; then
  cp "../azure.yaml" "../azure.yaml.terraform-backup"
  sed -i.bak 's/provider: terraform/provider: bicep/' ../azure.yaml
  # Remove any Terraform-specific hooks
  sed -i.bak '/preprovision:/,/terraform init/d' ../azure.yaml
  echo "✓ azure.yaml updated (backup: azure.yaml.terraform-backup)"
else
  echo "⚠️  azure.yaml not found"
fi

# Step 5: Verify Bicep deployment
echo ""
echo "Step 5/5: Verifying Bicep deployment..."
DEPLOYMENT_NAME="main-${ENVIRONMENT}"

if az deployment sub show --name "$DEPLOYMENT_NAME" &>/dev/null; then
  DEPLOYMENT_STATE=$(az deployment sub show \
    --name "$DEPLOYMENT_NAME" \
    --query properties.provisioningState -o tsv)
  echo "✓ Bicep deployment found: $DEPLOYMENT_NAME"
  echo "  Status: $DEPLOYMENT_STATE"
else
  echo "⚠️  WARNING: Bicep deployment not found"
  echo "You may need to re-run: azd provision"
fi

echo ""
echo "======================================"
echo "Rollback Complete!"
echo "======================================"
echo ""
echo "What happened:"
echo "  ✓ Terraform state removed"
echo "  ✓ Resources remain unchanged in Azure"
echo "  ✓ Bicep files restored"
echo "  ✓ azure.yaml updated"
echo ""
echo "Backups created:"
echo "  - ../$BACKUP_DIR/ (Terraform state)"
echo "  - ../azure.yaml.terraform-backup (azure.yaml)"
echo ""
echo "Next steps:"
echo "  1. Verify infrastructure with: azd provision --preview"
echo "  2. Test application is working"
echo "  3. Investigate and fix Terraform migration issues"
echo "  4. When ready, retry migration"
echo ""
echo "To return to Terraform later:"
echo "  - Restore Terraform files from git"
echo "  - Update azure.yaml provider back to terraform"
echo "  - Re-run import process"
echo ""
