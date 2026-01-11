"use client";

import { ApplicationInsights, ITelemetryItem } from "@microsoft/applicationinsights-web";

let appInsights: ApplicationInsights | null = null;

export function initAppInsights(): ApplicationInsights | null {
  // Only initialize in browser and if connection string is available
  if (typeof window === "undefined") return null;
  
  const connectionString = process.env.NEXT_PUBLIC_APPLICATIONINSIGHTS_CONNECTION_STRING;
  
  if (!connectionString) {
    console.log("Application Insights not configured - skipping initialization");
    return null;
  }

  if (appInsights) {
    return appInsights;
  }

  appInsights = new ApplicationInsights({
    config: {
      connectionString,
      enableAutoRouteTracking: true, // Track page views automatically
      enableCorsCorrelation: true, // Correlate requests with backend
      enableRequestHeaderTracking: true,
      enableResponseHeaderTracking: true,
      enableAjaxPerfTracking: true,
      maxAjaxCallsPerView: 500,
      disableFetchTracking: false,
      autoTrackPageVisitTime: true,
      // Privacy - don't track user agent by default
      isStorageUseDisabled: false,
      isCookieUseDisabled: false,
    },
  });

  appInsights.loadAppInsights();

  // Add custom telemetry initializer to enrich data
  appInsights.addTelemetryInitializer((item: ITelemetryItem) => {
    // Add custom properties to all telemetry
    item.data = item.data || {};
    item.data.appName = "learn-to-cloud-frontend";
    return true;
  });

  return appInsights;
}

export function getAppInsights(): ApplicationInsights | null {
  return appInsights;
}

// Helper to track custom events
export function trackEvent(name: string, properties?: Record<string, string>) {
  appInsights?.trackEvent({ name }, properties);
}

// Helper to track exceptions
export function trackException(error: Error, properties?: Record<string, string>) {
  appInsights?.trackException({ exception: error }, properties);
}

// Helper to track page views (usually auto-tracked, but useful for SPAs)
export function trackPageView(name?: string, uri?: string) {
  appInsights?.trackPageView({ name, uri });
}
