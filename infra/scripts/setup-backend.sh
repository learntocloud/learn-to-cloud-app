#!/bin/bash
# Setup Azure Storage Account for Terraform Backend
# This script creates a storage account and container for Terraform state files

set -e

echo "======================================"
echo "Terraform Backend Setup"
echo "======================================"
echo ""

# Configuration
RESOURCE_GROUP="rg-terraform-state"
LOCATION="${1:-eastus}"
STORAGE_ACCOUNT="stterraformstate$(openssl rand -hex 4)"
CONTAINER_NAME="tfstate"

echo "Creating resources with the following configuration:"
echo "  Resource Group:    $RESOURCE_GROUP"
echo "  Location:          $LOCATION"
echo "  Storage Account:   $STORAGE_ACCOUNT"
echo "  Container:         $CONTAINER_NAME"
echo ""

# Create resource group for Terraform state
echo "Creating resource group..."
az group create \
  --name "$RESOURCE_GROUP" \
  --location "$LOCATION" \
  --output none

echo "✓ Resource group created"

# Create storage account with versioning and encryption
echo "Creating storage account..."
az storage account create \
  --name "$STORAGE_ACCOUNT" \
  --resource-group "$RESOURCE_GROUP" \
  --location "$LOCATION" \
  --sku Standard_LRS \
  --encryption-services blob \
  --allow-blob-public-access false \
  --min-tls-version TLS1_2 \
  --output none

echo "✓ Storage account created"

# Enable versioning for state file protection
echo "Enabling blob versioning..."
az storage account blob-service-properties update \
  --account-name "$STORAGE_ACCOUNT" \
  --resource-group "$RESOURCE_GROUP" \
  --enable-versioning true \
  --output none

echo "✓ Blob versioning enabled"

# Create container for state files
echo "Creating blob container..."
az storage container create \
  --name "$CONTAINER_NAME" \
  --account-name "$STORAGE_ACCOUNT" \
  --auth-mode login \
  --output none

echo "✓ Blob container created"

# Get storage account key
ACCOUNT_KEY=$(az storage account keys list \
  --resource-group "$RESOURCE_GROUP" \
  --account-name "$STORAGE_ACCOUNT" \
  --query '[0].value' -o tsv)

echo ""
echo "======================================"
echo "Backend Setup Complete!"
echo "======================================"
echo ""
echo "Add this to your infra/backend.tf file:"
echo ""
echo "terraform {"
echo "  backend \"azurerm\" {"
echo "    resource_group_name  = \"$RESOURCE_GROUP\""
echo "    storage_account_name = \"$STORAGE_ACCOUNT\""
echo "    container_name       = \"$CONTAINER_NAME\""
echo "    key                  = \"learn-to-cloud-dev.tfstate\""
echo "  }"
echo "}"
echo ""
echo "Set this environment variable:"
echo "  export ARM_ACCESS_KEY=\"$ACCOUNT_KEY\""
echo ""
echo "Or save it securely in your .env file"
echo ""
echo "Then run: terraform init"
echo ""
