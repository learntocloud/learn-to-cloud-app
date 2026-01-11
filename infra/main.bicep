// Azure Infrastructure for Learn to Cloud App
// Deploy with: az deployment sub create --location eastus2 --template-file main.bicep

targetScope = 'subscription'

@description('The environment name (dev, staging, prod)')
param environment string = 'dev'

@description('The Azure region for resources')
param location string

@description('PostgreSQL admin password')
@secure()
param postgresAdminPassword string

@description('Clerk Secret Key')
@secure()
param clerkSecretKey string

@description('Clerk Webhook Signing Secret')
@secure()
param clerkWebhookSigningSecret string

@description('Clerk Publishable Key')
param clerkPublishableKey string

@description('Custom domain for the frontend app (optional)')
param frontendCustomDomain string = ''

var resourceGroupName = 'rg-learntocloud-${environment}'
var tags = {
  environment: environment
  project: 'learn-to-cloud'
}

// Resource Group
resource rg 'Microsoft.Resources/resourceGroups@2023-07-01' = {
  name: resourceGroupName
  location: location
  tags: tags
}

// Deploy all resources in the resource group
module resources 'resources.bicep' = {
  name: 'resources-${environment}'
  scope: rg
  params: {
    environment: environment
    location: location
    tags: tags
    postgresAdminPassword: postgresAdminPassword
    clerkSecretKey: clerkSecretKey
    clerkWebhookSigningSecret: clerkWebhookSigningSecret
    clerkPublishableKey: clerkPublishableKey
    frontendCustomDomain: frontendCustomDomain
  }
}

// Outputs for azd
output AZURE_RESOURCE_GROUP string = rg.name
output AZURE_LOCATION string = location

// Service endpoints
output apiUrl string = resources.outputs.apiUrl
output frontendUrl string = resources.outputs.frontendUrl
output postgresHost string = resources.outputs.postgresHost

// Service resource names for azd deploy
output AZURE_CONTAINER_REGISTRY_NAME string = resources.outputs.containerRegistryName
output AZURE_CONTAINER_REGISTRY_ENDPOINT string = resources.outputs.containerRegistryLoginServer
