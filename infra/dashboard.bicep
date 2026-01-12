// Azure Dashboard for Learn to Cloud App
// Provides monitoring overview for Container Apps, PostgreSQL, and Application Insights

@description('The environment name')
param environment string

@description('The Azure region')
param location string

@description('Resource tags')
param tags object

@description('Resource ID of the API Container App')
param apiAppId string

@description('Resource ID of the Frontend Container App')
param frontendAppId string

@description('Resource ID of the PostgreSQL Flexible Server')
param postgresServerId string

@description('Resource ID of Application Insights')
param appInsightsId string

@description('Resource ID of Log Analytics Workspace')
param logAnalyticsId string

var dashboardName = 'dashboard-learntocloud-${environment}'

resource dashboard 'Microsoft.Portal/dashboards@2020-09-01-preview' = {
  name: dashboardName
  location: location
  tags: union(tags, {
    'hidden-title': 'Learn to Cloud - ${environment}'
  })
  properties: {
    lenses: [
      {
        order: 0
        parts: [
          // Row 1: API Container App Metrics
          {
            position: {
              x: 0
              y: 0
              colSpan: 4
              rowSpan: 3
            }
            metadata: {
              type: 'Extension/HubsExtension/PartType/MonitorChartPart'
              inputs: [
                {
                  name: 'options'
                  value: {
                    chart: {
                      metrics: [
                        {
                          resourceMetadata: {
                            id: apiAppId
                          }
                          name: 'UsageNanoCores'
                          aggregationType: 4 // Average
                          namespace: 'Microsoft.App/containerApps'
                          metricVisualization: {
                            displayName: 'CPU Usage'
                            resourceDisplayName: 'API'
                          }
                        }
                      ]
                      title: 'API - CPU Usage'
                      titleKind: 1
                      visualization: {
                        chartType: 2 // Line chart
                        legendVisualization: {
                          isVisible: true
                          position: 2
                          hideSubtitle: false
                        }
                        axisVisualization: {
                          x: {
                            isVisible: true
                            axisType: 2
                          }
                          y: {
                            isVisible: true
                            axisType: 1
                          }
                        }
                      }
                      timespan: {
                        relative: {
                          duration: 86400000 // 24 hours
                        }
                        showUTCTime: false
                        grain: 1
                      }
                    }
                  }
                }
              ]
            }
          }
          {
            position: {
              x: 4
              y: 0
              colSpan: 4
              rowSpan: 3
            }
            metadata: {
              type: 'Extension/HubsExtension/PartType/MonitorChartPart'
              inputs: [
                {
                  name: 'options'
                  value: {
                    chart: {
                      metrics: [
                        {
                          resourceMetadata: {
                            id: apiAppId
                          }
                          name: 'WorkingSetBytes'
                          aggregationType: 4 // Average
                          namespace: 'Microsoft.App/containerApps'
                          metricVisualization: {
                            displayName: 'Memory Working Set'
                            resourceDisplayName: 'API'
                          }
                        }
                      ]
                      title: 'API - Memory Usage'
                      titleKind: 1
                      visualization: {
                        chartType: 2
                        legendVisualization: {
                          isVisible: true
                          position: 2
                          hideSubtitle: false
                        }
                        axisVisualization: {
                          x: {
                            isVisible: true
                            axisType: 2
                          }
                          y: {
                            isVisible: true
                            axisType: 1
                          }
                        }
                      }
                      timespan: {
                        relative: {
                          duration: 86400000
                        }
                        showUTCTime: false
                        grain: 1
                      }
                    }
                  }
                }
              ]
            }
          }
          {
            position: {
              x: 8
              y: 0
              colSpan: 4
              rowSpan: 3
            }
            metadata: {
              type: 'Extension/HubsExtension/PartType/MonitorChartPart'
              inputs: [
                {
                  name: 'options'
                  value: {
                    chart: {
                      metrics: [
                        {
                          resourceMetadata: {
                            id: apiAppId
                          }
                          name: 'Replicas'
                          aggregationType: 4 // Average
                          namespace: 'Microsoft.App/containerApps'
                          metricVisualization: {
                            displayName: 'Replica Count'
                            resourceDisplayName: 'API'
                          }
                        }
                      ]
                      title: 'API - Replica Count'
                      titleKind: 1
                      visualization: {
                        chartType: 2
                        legendVisualization: {
                          isVisible: true
                          position: 2
                          hideSubtitle: false
                        }
                        axisVisualization: {
                          x: {
                            isVisible: true
                            axisType: 2
                          }
                          y: {
                            isVisible: true
                            axisType: 1
                          }
                        }
                      }
                      timespan: {
                        relative: {
                          duration: 86400000
                        }
                        showUTCTime: false
                        grain: 1
                      }
                    }
                  }
                }
              ]
            }
          }
          {
            position: {
              x: 12
              y: 0
              colSpan: 4
              rowSpan: 3
            }
            metadata: {
              type: 'Extension/HubsExtension/PartType/MonitorChartPart'
              inputs: [
                {
                  name: 'options'
                  value: {
                    chart: {
                      metrics: [
                        {
                          resourceMetadata: {
                            id: apiAppId
                          }
                          name: 'Requests'
                          aggregationType: 1 // Total
                          namespace: 'Microsoft.App/containerApps'
                          metricVisualization: {
                            displayName: 'Total Requests'
                            resourceDisplayName: 'API'
                          }
                        }
                      ]
                      title: 'API - Request Count'
                      titleKind: 1
                      visualization: {
                        chartType: 2
                        legendVisualization: {
                          isVisible: true
                          position: 2
                          hideSubtitle: false
                        }
                        axisVisualization: {
                          x: {
                            isVisible: true
                            axisType: 2
                          }
                          y: {
                            isVisible: true
                            axisType: 1
                          }
                        }
                      }
                      timespan: {
                        relative: {
                          duration: 86400000
                        }
                        showUTCTime: false
                        grain: 1
                      }
                    }
                  }
                }
              ]
            }
          }

          // Row 2: API Errors and Response Times
          {
            position: {
              x: 0
              y: 3
              colSpan: 6
              rowSpan: 3
            }
            metadata: {
              type: 'Extension/HubsExtension/PartType/MonitorChartPart'
              inputs: [
                {
                  name: 'options'
                  value: {
                    chart: {
                      metrics: [
                        {
                          resourceMetadata: {
                            id: apiAppId
                          }
                          name: 'Requests'
                          aggregationType: 1 // Total
                          namespace: 'Microsoft.App/containerApps'
                          metricVisualization: {
                            displayName: 'Requests by Status'
                            resourceDisplayName: 'API'
                          }
                        }
                      ]
                      title: 'API - Requests by Status Code'
                      titleKind: 1
                      visualization: {
                        chartType: 2
                        legendVisualization: {
                          isVisible: true
                          position: 2
                          hideSubtitle: false
                        }
                        axisVisualization: {
                          x: {
                            isVisible: true
                            axisType: 2
                          }
                          y: {
                            isVisible: true
                            axisType: 1
                          }
                        }
                      }
                      grouping: {
                        dimension: 'statusCodeCategory'
                        sort: 2
                        top: 10
                      }
                      timespan: {
                        relative: {
                          duration: 86400000
                        }
                        showUTCTime: false
                        grain: 1
                      }
                    }
                  }
                }
              ]
            }
          }
          {
            position: {
              x: 6
              y: 3
              colSpan: 6
              rowSpan: 3
            }
            metadata: {
              type: 'Extension/HubsExtension/PartType/MonitorChartPart'
              inputs: [
                {
                  name: 'options'
                  value: {
                    chart: {
                      metrics: [
                        {
                          resourceMetadata: {
                            id: appInsightsId
                          }
                          name: 'requests/duration'
                          aggregationType: 4 // Average
                          namespace: 'microsoft.insights/components'
                          metricVisualization: {
                            displayName: 'Avg Response Time'
                            resourceDisplayName: 'App Insights'
                          }
                        }
                      ]
                      title: 'API - Response Time (App Insights)'
                      titleKind: 1
                      visualization: {
                        chartType: 2
                        legendVisualization: {
                          isVisible: true
                          position: 2
                          hideSubtitle: false
                        }
                        axisVisualization: {
                          x: {
                            isVisible: true
                            axisType: 2
                          }
                          y: {
                            isVisible: true
                            axisType: 1
                          }
                        }
                      }
                      timespan: {
                        relative: {
                          duration: 86400000
                        }
                        showUTCTime: false
                        grain: 1
                      }
                    }
                  }
                }
              ]
            }
          }
          {
            position: {
              x: 12
              y: 3
              colSpan: 4
              rowSpan: 3
            }
            metadata: {
              type: 'Extension/HubsExtension/PartType/MonitorChartPart'
              inputs: [
                {
                  name: 'options'
                  value: {
                    chart: {
                      metrics: [
                        {
                          resourceMetadata: {
                            id: appInsightsId
                          }
                          name: 'requests/failed'
                          aggregationType: 1 // Total
                          namespace: 'microsoft.insights/components'
                          metricVisualization: {
                            displayName: 'Failed Requests'
                            resourceDisplayName: 'App Insights'
                          }
                        }
                      ]
                      title: 'API - Failed Requests'
                      titleKind: 1
                      visualization: {
                        chartType: 2
                        legendVisualization: {
                          isVisible: true
                          position: 2
                          hideSubtitle: false
                        }
                        axisVisualization: {
                          x: {
                            isVisible: true
                            axisType: 2
                          }
                          y: {
                            isVisible: true
                            axisType: 1
                          }
                        }
                      }
                      timespan: {
                        relative: {
                          duration: 86400000
                        }
                        showUTCTime: false
                        grain: 1
                      }
                    }
                  }
                }
              ]
            }
          }

          // Row 3: PostgreSQL Database Metrics
          {
            position: {
              x: 0
              y: 6
              colSpan: 4
              rowSpan: 3
            }
            metadata: {
              type: 'Extension/HubsExtension/PartType/MonitorChartPart'
              inputs: [
                {
                  name: 'options'
                  value: {
                    chart: {
                      metrics: [
                        {
                          resourceMetadata: {
                            id: postgresServerId
                          }
                          name: 'cpu_percent'
                          aggregationType: 4 // Average
                          namespace: 'Microsoft.DBforPostgreSQL/flexibleServers'
                          metricVisualization: {
                            displayName: 'CPU Percent'
                            resourceDisplayName: 'PostgreSQL'
                          }
                        }
                      ]
                      title: 'PostgreSQL - CPU %'
                      titleKind: 1
                      visualization: {
                        chartType: 2
                        legendVisualization: {
                          isVisible: true
                          position: 2
                          hideSubtitle: false
                        }
                        axisVisualization: {
                          x: {
                            isVisible: true
                            axisType: 2
                          }
                          y: {
                            isVisible: true
                            axisType: 1
                          }
                        }
                      }
                      timespan: {
                        relative: {
                          duration: 86400000
                        }
                        showUTCTime: false
                        grain: 1
                      }
                    }
                  }
                }
              ]
            }
          }
          {
            position: {
              x: 4
              y: 6
              colSpan: 4
              rowSpan: 3
            }
            metadata: {
              type: 'Extension/HubsExtension/PartType/MonitorChartPart'
              inputs: [
                {
                  name: 'options'
                  value: {
                    chart: {
                      metrics: [
                        {
                          resourceMetadata: {
                            id: postgresServerId
                          }
                          name: 'memory_percent'
                          aggregationType: 4 // Average
                          namespace: 'Microsoft.DBforPostgreSQL/flexibleServers'
                          metricVisualization: {
                            displayName: 'Memory Percent'
                            resourceDisplayName: 'PostgreSQL'
                          }
                        }
                      ]
                      title: 'PostgreSQL - Memory %'
                      titleKind: 1
                      visualization: {
                        chartType: 2
                        legendVisualization: {
                          isVisible: true
                          position: 2
                          hideSubtitle: false
                        }
                        axisVisualization: {
                          x: {
                            isVisible: true
                            axisType: 2
                          }
                          y: {
                            isVisible: true
                            axisType: 1
                          }
                        }
                      }
                      timespan: {
                        relative: {
                          duration: 86400000
                        }
                        showUTCTime: false
                        grain: 1
                      }
                    }
                  }
                }
              ]
            }
          }
          {
            position: {
              x: 8
              y: 6
              colSpan: 4
              rowSpan: 3
            }
            metadata: {
              type: 'Extension/HubsExtension/PartType/MonitorChartPart'
              inputs: [
                {
                  name: 'options'
                  value: {
                    chart: {
                      metrics: [
                        {
                          resourceMetadata: {
                            id: postgresServerId
                          }
                          name: 'active_connections'
                          aggregationType: 4 // Average
                          namespace: 'Microsoft.DBforPostgreSQL/flexibleServers'
                          metricVisualization: {
                            displayName: 'Active Connections'
                            resourceDisplayName: 'PostgreSQL'
                          }
                        }
                      ]
                      title: 'PostgreSQL - Active Connections'
                      titleKind: 1
                      visualization: {
                        chartType: 2
                        legendVisualization: {
                          isVisible: true
                          position: 2
                          hideSubtitle: false
                        }
                        axisVisualization: {
                          x: {
                            isVisible: true
                            axisType: 2
                          }
                          y: {
                            isVisible: true
                            axisType: 1
                          }
                        }
                      }
                      timespan: {
                        relative: {
                          duration: 86400000
                        }
                        showUTCTime: false
                        grain: 1
                      }
                    }
                  }
                }
              ]
            }
          }
          {
            position: {
              x: 12
              y: 6
              colSpan: 4
              rowSpan: 3
            }
            metadata: {
              type: 'Extension/HubsExtension/PartType/MonitorChartPart'
              inputs: [
                {
                  name: 'options'
                  value: {
                    chart: {
                      metrics: [
                        {
                          resourceMetadata: {
                            id: postgresServerId
                          }
                          name: 'storage_used'
                          aggregationType: 4 // Average
                          namespace: 'Microsoft.DBforPostgreSQL/flexibleServers'
                          metricVisualization: {
                            displayName: 'Storage Used'
                            resourceDisplayName: 'PostgreSQL'
                          }
                        }
                      ]
                      title: 'PostgreSQL - Storage Used'
                      titleKind: 1
                      visualization: {
                        chartType: 2
                        legendVisualization: {
                          isVisible: true
                          position: 2
                          hideSubtitle: false
                        }
                        axisVisualization: {
                          x: {
                            isVisible: true
                            axisType: 2
                          }
                          y: {
                            isVisible: true
                            axisType: 1
                          }
                        }
                      }
                      timespan: {
                        relative: {
                          duration: 86400000
                        }
                        showUTCTime: false
                        grain: 1
                      }
                    }
                  }
                }
              ]
            }
          }

          // Row 4: Frontend Container App Metrics
          {
            position: {
              x: 0
              y: 9
              colSpan: 4
              rowSpan: 3
            }
            metadata: {
              type: 'Extension/HubsExtension/PartType/MonitorChartPart'
              inputs: [
                {
                  name: 'options'
                  value: {
                    chart: {
                      metrics: [
                        {
                          resourceMetadata: {
                            id: frontendAppId
                          }
                          name: 'UsageNanoCores'
                          aggregationType: 4 // Average
                          namespace: 'Microsoft.App/containerApps'
                          metricVisualization: {
                            displayName: 'CPU Usage'
                            resourceDisplayName: 'Frontend'
                          }
                        }
                      ]
                      title: 'Frontend - CPU Usage'
                      titleKind: 1
                      visualization: {
                        chartType: 2
                        legendVisualization: {
                          isVisible: true
                          position: 2
                          hideSubtitle: false
                        }
                        axisVisualization: {
                          x: {
                            isVisible: true
                            axisType: 2
                          }
                          y: {
                            isVisible: true
                            axisType: 1
                          }
                        }
                      }
                      timespan: {
                        relative: {
                          duration: 86400000
                        }
                        showUTCTime: false
                        grain: 1
                      }
                    }
                  }
                }
              ]
            }
          }
          {
            position: {
              x: 4
              y: 9
              colSpan: 4
              rowSpan: 3
            }
            metadata: {
              type: 'Extension/HubsExtension/PartType/MonitorChartPart'
              inputs: [
                {
                  name: 'options'
                  value: {
                    chart: {
                      metrics: [
                        {
                          resourceMetadata: {
                            id: frontendAppId
                          }
                          name: 'WorkingSetBytes'
                          aggregationType: 4 // Average
                          namespace: 'Microsoft.App/containerApps'
                          metricVisualization: {
                            displayName: 'Memory Working Set'
                            resourceDisplayName: 'Frontend'
                          }
                        }
                      ]
                      title: 'Frontend - Memory Usage'
                      titleKind: 1
                      visualization: {
                        chartType: 2
                        legendVisualization: {
                          isVisible: true
                          position: 2
                          hideSubtitle: false
                        }
                        axisVisualization: {
                          x: {
                            isVisible: true
                            axisType: 2
                          }
                          y: {
                            isVisible: true
                            axisType: 1
                          }
                        }
                      }
                      timespan: {
                        relative: {
                          duration: 86400000
                        }
                        showUTCTime: false
                        grain: 1
                      }
                    }
                  }
                }
              ]
            }
          }
          {
            position: {
              x: 8
              y: 9
              colSpan: 4
              rowSpan: 3
            }
            metadata: {
              type: 'Extension/HubsExtension/PartType/MonitorChartPart'
              inputs: [
                {
                  name: 'options'
                  value: {
                    chart: {
                      metrics: [
                        {
                          resourceMetadata: {
                            id: frontendAppId
                          }
                          name: 'Requests'
                          aggregationType: 1 // Total
                          namespace: 'Microsoft.App/containerApps'
                          metricVisualization: {
                            displayName: 'Total Requests'
                            resourceDisplayName: 'Frontend'
                          }
                        }
                      ]
                      title: 'Frontend - Request Count'
                      titleKind: 1
                      visualization: {
                        chartType: 2
                        legendVisualization: {
                          isVisible: true
                          position: 2
                          hideSubtitle: false
                        }
                        axisVisualization: {
                          x: {
                            isVisible: true
                            axisType: 2
                          }
                          y: {
                            isVisible: true
                            axisType: 1
                          }
                        }
                      }
                      timespan: {
                        relative: {
                          duration: 86400000
                        }
                        showUTCTime: false
                        grain: 1
                      }
                    }
                  }
                }
              ]
            }
          }
          {
            position: {
              x: 12
              y: 9
              colSpan: 4
              rowSpan: 3
            }
            metadata: {
              type: 'Extension/HubsExtension/PartType/MonitorChartPart'
              inputs: [
                {
                  name: 'options'
                  value: {
                    chart: {
                      metrics: [
                        {
                          resourceMetadata: {
                            id: frontendAppId
                          }
                          name: 'Requests'
                          aggregationType: 1 // Total
                          namespace: 'Microsoft.App/containerApps'
                          metricVisualization: {
                            displayName: 'Requests by Status'
                            resourceDisplayName: 'Frontend'
                          }
                        }
                      ]
                      title: 'Frontend - Requests by Status'
                      titleKind: 1
                      visualization: {
                        chartType: 2
                        legendVisualization: {
                          isVisible: true
                          position: 2
                          hideSubtitle: false
                        }
                        axisVisualization: {
                          x: {
                            isVisible: true
                            axisType: 2
                          }
                          y: {
                            isVisible: true
                            axisType: 1
                          }
                        }
                      }
                      grouping: {
                        dimension: 'statusCodeCategory'
                        sort: 2
                        top: 10
                      }
                      timespan: {
                        relative: {
                          duration: 86400000
                        }
                        showUTCTime: false
                        grain: 1
                      }
                    }
                  }
                }
              ]
            }
          }

          // Row 5: Dependencies and Log Analytics
          {
            position: {
              x: 0
              y: 12
              colSpan: 6
              rowSpan: 3
            }
            metadata: {
              type: 'Extension/HubsExtension/PartType/MonitorChartPart'
              inputs: [
                {
                  name: 'options'
                  value: {
                    chart: {
                      metrics: [
                        {
                          resourceMetadata: {
                            id: appInsightsId
                          }
                          name: 'dependencies/duration'
                          aggregationType: 4 // Average
                          namespace: 'microsoft.insights/components'
                          metricVisualization: {
                            displayName: 'Dependency Duration'
                            resourceDisplayName: 'App Insights'
                          }
                        }
                      ]
                      title: 'Dependency Call Duration (DB, External APIs)'
                      titleKind: 1
                      visualization: {
                        chartType: 2
                        legendVisualization: {
                          isVisible: true
                          position: 2
                          hideSubtitle: false
                        }
                        axisVisualization: {
                          x: {
                            isVisible: true
                            axisType: 2
                          }
                          y: {
                            isVisible: true
                            axisType: 1
                          }
                        }
                      }
                      timespan: {
                        relative: {
                          duration: 86400000
                        }
                        showUTCTime: false
                        grain: 1
                      }
                    }
                  }
                }
              ]
            }
          }
          {
            position: {
              x: 6
              y: 12
              colSpan: 6
              rowSpan: 3
            }
            metadata: {
              type: 'Extension/HubsExtension/PartType/MonitorChartPart'
              inputs: [
                {
                  name: 'options'
                  value: {
                    chart: {
                      metrics: [
                        {
                          resourceMetadata: {
                            id: appInsightsId
                          }
                          name: 'dependencies/failed'
                          aggregationType: 1 // Total
                          namespace: 'microsoft.insights/components'
                          metricVisualization: {
                            displayName: 'Failed Dependencies'
                            resourceDisplayName: 'App Insights'
                          }
                        }
                      ]
                      title: 'Failed Dependency Calls'
                      titleKind: 1
                      visualization: {
                        chartType: 2
                        legendVisualization: {
                          isVisible: true
                          position: 2
                          hideSubtitle: false
                        }
                        axisVisualization: {
                          x: {
                            isVisible: true
                            axisType: 2
                          }
                          y: {
                            isVisible: true
                            axisType: 1
                          }
                        }
                      }
                      timespan: {
                        relative: {
                          duration: 86400000
                        }
                        showUTCTime: false
                        grain: 1
                      }
                    }
                  }
                }
              ]
            }
          }
          // Markdown tile for dashboard info
          {
            position: {
              x: 12
              y: 12
              colSpan: 4
              rowSpan: 3
            }
            metadata: {
              type: 'Extension/HubsExtension/PartType/MarkdownPart'
              inputs: []
              settings: {
                content: {
                  content: '## Learn to Cloud\n### ${environment} Environment\n\n**Quick Links:**\n- [Application Insights](https://portal.azure.com/#blade/HubsExtension/BrowseResource/resourceType/microsoft.insights%2Fcomponents)\n- [Log Analytics](https://portal.azure.com/#blade/HubsExtension/BrowseResource/resourceType/Microsoft.OperationalInsights%2Fworkspaces)\n- [Alerts](https://portal.azure.com/#blade/Microsoft_Azure_Monitoring/AzureMonitoringBrowseBlade/alertsV2)\n\n**Timespan:** Last 24 hours'
                  title: 'Dashboard Info'
                  subtitle: ''
                  markdownSource: 1
                  markdownUri: ''
                }
              }
            }
          }
        ]
      }
    ]
    metadata: {
      model: {
        timeRange: {
          value: {
            relative: {
              duration: 24
              timeUnit: 1
            }
          }
          type: 'MsPortalFx.Composition.Configuration.ValueTypes.TimeRange'
        }
        filterLocale: {
          value: 'en-us'
        }
        filters: {
          value: {
            MsPortalFx_TimeRange: {
              model: {
                format: 'utc'
                granularity: 'auto'
                relative: '24h'
              }
              displayCache: {
                name: 'UTC Time'
                value: 'Past 24 hours'
              }
            }
          }
        }
      }
    }
  }
}

output dashboardId string = dashboard.id
output dashboardName string = dashboard.name
