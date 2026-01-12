// Azure Resources for Learn to Cloud App
// Dual Container Apps architecture: frontend (Next.js) + api (FastAPI)

@description('The environment name')
param environment string

@description('The Azure region')
param location string

@description('Resource tags')
param tags object

@description('PostgreSQL administrator password')
@secure()
param postgresAdminPassword string

@description('Clerk secret key for backend authentication')
@secure()
param clerkSecretKey string

@description('Clerk webhook signing secret for verifying webhook payloads')
@secure()
param clerkWebhookSigningSecret string

@description('Clerk publishable key for frontend authentication')
param clerkPublishableKey string

@description('Custom domain for the frontend app (optional)')
param frontendCustomDomain string = ''

@description('Name of the existing managed certificate resource in the Container Apps environment (required when binding a custom domain)')
param frontendManagedCertificateName string = ''

var uniqueSuffix = uniqueString(resourceGroup().id)
var appName = 'learntocloud'
var apiAppName = 'ca-${appName}-api-${environment}'
var frontendAppName = 'ca-${appName}-frontend-${environment}'

// Log Analytics Workspace
resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: 'log-${appName}-${environment}'
  location: location
  tags: tags
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 30
  }
}

// Application Insights
resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: 'appi-${appName}-${environment}'
  location: location
  tags: tags
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logAnalytics.id
  }
}

// PostgreSQL Flexible Server
resource postgres 'Microsoft.DBforPostgreSQL/flexibleServers@2023-12-01-preview' = {
  name: 'psql-${appName}-${environment}-${uniqueSuffix}'
  location: location
  tags: tags
  sku: {
    name: 'Standard_B1ms'
    tier: 'Burstable'
  }
  properties: {
    version: '16'
    administratorLogin: 'ltcadmin'
    administratorLoginPassword: postgresAdminPassword
    authConfig: {
      activeDirectoryAuth: 'Enabled'
      passwordAuth: 'Enabled'  // Keep password auth enabled for admin/migration tasks
    }
    storage: {
      storageSizeGB: 32
      autoGrow: 'Enabled'
    }
    backup: {
      backupRetentionDays: 7
      geoRedundantBackup: 'Disabled'
    }
    highAvailability: {
      mode: 'Disabled'
    }
  }
}

// PostgreSQL Database
resource database 'Microsoft.DBforPostgreSQL/flexibleServers/databases@2023-12-01-preview' = {
  parent: postgres
  name: 'learntocloud'
  properties: {
    charset: 'UTF8'
    collation: 'en_US.utf8'
  }
}

// PostgreSQL Firewall Rule (allow Azure services)
resource postgresFirewall 'Microsoft.DBforPostgreSQL/flexibleServers/firewallRules@2023-12-01-preview' = {
  parent: postgres
  name: 'AllowAzureServices'
  properties: {
    startIpAddress: '0.0.0.0'
    endIpAddress: '0.0.0.0'
  }
}

// Azure Container Registry
resource containerRegistry 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: 'crltc${uniqueSuffix}'
  location: location
  tags: tags
  sku: {
    name: 'Basic'
  }
  properties: {
    adminUserEnabled: false
  }
}

// Container Apps Environment
resource containerAppsEnvironment 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: 'cae-${appName}-${environment}'
  location: location
  tags: tags
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalytics.properties.customerId
        sharedKey: logAnalytics.listKeys().primarySharedKey
      }
    }
  }
}

var apiDefaultUrl = 'https://${apiAppName}.${containerAppsEnvironment.properties.defaultDomain}'
var frontendDefaultUrl = 'https://${frontendAppName}.${containerAppsEnvironment.properties.defaultDomain}'
var apiCorsAllowedOrigins = concat(
  [
    frontendDefaultUrl
    'http://localhost:3000'
  ],
  !empty(frontendCustomDomain) ? [
    'https://${frontendCustomDomain}'
  ] : []
)

// Reference existing Managed Certificate for custom domain (created manually via Azure CLI)
// Certificate name follows Azure's auto-generated naming: {hostname}-{env-prefix}-{timestamp}
resource managedCertificate 'Microsoft.App/managedEnvironments/managedCertificates@2024-03-01' existing = if (!empty(frontendCustomDomain) && !empty(frontendManagedCertificateName)) {
  parent: containerAppsEnvironment
  name: frontendManagedCertificateName
}

// API Container App (FastAPI)
resource apiApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: apiAppName
  location: location
  tags: union(tags, { 'azd-service-name': 'api' })
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    managedEnvironmentId: containerAppsEnvironment.id
    configuration: {
      ingress: {
        external: true
        targetPort: 8000
        transport: 'http'
        allowInsecure: false
        corsPolicy: {
          allowedOrigins: apiCorsAllowedOrigins
          allowedMethods: ['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS']
          allowedHeaders: ['*']
          allowCredentials: true
        }
      }
      registries: [
        {
          server: containerRegistry.properties.loginServer
          identity: 'system'
        }
      ]
      secrets: [
        {
          name: 'clerk-secret-key'
          value: clerkSecretKey
        }
        {
          name: 'clerk-webhook-signing-secret'
          value: clerkWebhookSigningSecret
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'api'
          image: 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest'
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
          env: [
            {
              name: 'POSTGRES_HOST'
              value: postgres.properties.fullyQualifiedDomainName
            }
            {
              name: 'POSTGRES_DATABASE'
              value: 'learntocloud'
            }
            {
              name: 'POSTGRES_USER'
              value: apiAppName  // Use managed identity name for Entra auth
            }
            {
              name: 'CLERK_SECRET_KEY'
              secretRef: 'clerk-secret-key'
            }
            {
              name: 'CLERK_WEBHOOK_SIGNING_SECRET'
              secretRef: 'clerk-webhook-signing-secret'
            }
            {
              name: 'CLERK_PUBLISHABLE_KEY'
              value: clerkPublishableKey
            }
            {
              name: 'ENVIRONMENT'
              value: environment
            }
            {
              name: 'FRONTEND_URL'
              value: !empty(frontendCustomDomain) ? 'https://${frontendCustomDomain}' : frontendDefaultUrl
            }
            {
              name: 'APPLICATIONINSIGHTS_CONNECTION_STRING'
              value: appInsights.properties.ConnectionString
            }
          ]
          // Health probes - allow longer startup for cold starts
          probes: [
            {
              type: 'Startup'
              httpGet: {
                path: '/health'
                port: 8000
              }
              initialDelaySeconds: 5
              periodSeconds: 10
              failureThreshold: 30  // Allow up to 5 minutes for cold start
              timeoutSeconds: 3
            }
            {
              type: 'Liveness'
              httpGet: {
                path: '/health'
                port: 8000
              }
              initialDelaySeconds: 0
              periodSeconds: 30
              failureThreshold: 3
              timeoutSeconds: 5
            }
            {
              type: 'Readiness'
              httpGet: {
                path: '/ready'
                port: 8000
              }
              initialDelaySeconds: 0
              periodSeconds: 10
              failureThreshold: 3
              timeoutSeconds: 3
            }
          ]
        }
      ]
      scale: {
        minReplicas: 0  // Scale to zero when idle (cost savings)
        maxReplicas: 10
        rules: [
          {
            name: 'http-scaling'
            http: {
              metadata: {
                concurrentRequests: '50'  // Scale up sooner for better latency
              }
            }
          }
        ]
      }
    }
  }
}

// NOTE: PostgreSQL Entra Admin is configured via Azure CLI in GitHub Actions workflow
// The API container app's managed identity needs to be added as a PostgreSQL admin
// This is done post-deployment because the principal ID isn't known until the container app is created

// Frontend Container App (Next.js)
resource frontendApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: frontendAppName
  location: location
  tags: union(tags, { 'azd-service-name': 'frontend' })
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    managedEnvironmentId: containerAppsEnvironment.id
    configuration: {
      ingress: {
        external: true
        targetPort: 3000
        transport: 'http'
        allowInsecure: false
        customDomains: (!empty(frontendCustomDomain) && !empty(frontendManagedCertificateName)) ? [
          {
            name: frontendCustomDomain
            bindingType: 'SniEnabled'
            certificateId: managedCertificate.id
          }
        ] : []
      }
      registries: [
        {
          server: containerRegistry.properties.loginServer
          identity: 'system'
        }
      ]
      secrets: [
        {
          name: 'clerk-secret-key'
          value: clerkSecretKey
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'frontend'
          image: 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest'
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
          env: [
            {
              name: 'NEXT_PUBLIC_API_URL'
              value: apiDefaultUrl
            }
            {
              name: 'NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY'
              value: clerkPublishableKey
            }
            {
              name: 'CLERK_SECRET_KEY'
              secretRef: 'clerk-secret-key'
            }
            {
              name: 'PORT'
              value: '3000'
            }
            {
              name: 'NEXT_PUBLIC_CLERK_SIGN_IN_URL'
              value: '/sign-in'
            }
            {
              name: 'NEXT_PUBLIC_CLERK_SIGN_UP_URL'
              value: '/sign-up'
            }
            {
              name: 'NEXT_PUBLIC_APPLICATIONINSIGHTS_CONNECTION_STRING'
              value: appInsights.properties.ConnectionString
            }
          ]
          // Health probes for frontend
          probes: [
            {
              type: 'Startup'
              httpGet: {
                path: '/'
                port: 3000
              }
              initialDelaySeconds: 5
              periodSeconds: 10
              failureThreshold: 30  // Allow up to 5 minutes for Next.js cold start
              timeoutSeconds: 3
            }
            {
              type: 'Liveness'
              httpGet: {
                path: '/'
                port: 3000
              }
              initialDelaySeconds: 0
              periodSeconds: 30
              failureThreshold: 3
              timeoutSeconds: 5
            }
            {
              type: 'Readiness'
              httpGet: {
                path: '/'
                port: 3000
              }
              initialDelaySeconds: 0
              periodSeconds: 10
              failureThreshold: 3
              timeoutSeconds: 3
            }
          ]
        }
      ]
      scale: {
        minReplicas: 0  // Scale to zero when idle (cost savings)
        maxReplicas: 10
        rules: [
          {
            name: 'http-scaling'
            http: {
              metadata: {
                concurrentRequests: '50'  // Scale up sooner for better latency
              }
            }
          }
        ]
      }
    }
  }
  dependsOn: [
    apiApp
  ]
}

var acrPullRoleDefinitionId = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '7f951dda-4ed3-4680-a7ca-43fe172d538d')

resource apiAcrPullRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(containerRegistry.id, apiApp.id, 'acrPull')
  scope: containerRegistry
  properties: {
    roleDefinitionId: acrPullRoleDefinitionId
    principalId: apiApp.identity.principalId
  }
}

resource frontendAcrPullRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(containerRegistry.id, frontendApp.id, 'acrPull')
  scope: containerRegistry
  properties: {
    roleDefinitionId: acrPullRoleDefinitionId
    principalId: frontendApp.identity.principalId
  }
}

// Outputs
output apiUrl string = 'https://${apiApp.properties.configuration.ingress.fqdn}'
output frontendUrl string = 'https://${frontendApp.properties.configuration.ingress.fqdn}'
output postgresHost string = postgres.properties.fullyQualifiedDomainName
output apiAppName string = apiApp.name
output frontendAppName string = frontendApp.name
output containerRegistryName string = containerRegistry.name
output containerRegistryLoginServer string = containerRegistry.properties.loginServer
