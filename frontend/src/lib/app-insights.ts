"use client";

// Lazy load Application Insights SDK to improve cold start time (~100KB saved from initial bundle)
type ApplicationInsightsType = import("@microsoft/applicationinsights-web").ApplicationInsights;
type ITelemetryItemType = import("@microsoft/applicationinsights-web").ITelemetryItem;

let appInsights: ApplicationInsightsType | null = null;
let initPromise: Promise<ApplicationInsightsType | null> | null = null;

export async function initAppInsights(): Promise<ApplicationInsightsType | null> {
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

  // Dedupe concurrent init calls
  if (initPromise) {
    return initPromise;
  }

  initPromise = (async () => {
    // Dynamically import the heavy SDK only when needed
    const { ApplicationInsights } = await import("@microsoft/applicationinsights-web");

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
    appInsights.addTelemetryInitializer((item: ITelemetryItemType) => {
      // Add custom properties to all telemetry
      item.data = item.data || {};
      item.data.appName = "learn-to-cloud-frontend";
      return true;
    });

    return appInsights;
  })();

  return initPromise;
}

export function getAppInsights(): ApplicationInsightsType | null {
  return appInsights;
}

// Helper to track custom events (fire-and-forget, won't block)
export function trackEvent(name: string, properties?: Record<string, string>) {
  appInsights?.trackEvent({ name }, properties);
}

// Helper to track exceptions (fire-and-forget, won't block)
export function trackException(error: Error, properties?: Record<string, string>) {
  appInsights?.trackException({ exception: error }, properties);
}

// Helper to track page views (usually auto-tracked, but useful for SPAs)
export function trackPageView(name?: string, uri?: string) {
  appInsights?.trackPageView({ name, uri });
}
