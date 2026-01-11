"use client";

import { useAuth } from "@clerk/nextjs";
import { trackEvent, getAppInsights } from "./app-insights";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/**
 * Track an API call with performance metrics.
 */
function trackApiCall(
  method: string,
  endpoint: string,
  durationMs: number,
  success: boolean,
  statusCode?: number
) {
  const appInsights = getAppInsights();
  if (!appInsights) return;

  // Track as a dependency call for proper performance analysis
  appInsights.trackDependencyData({
    id: crypto.randomUUID(),
    name: `${method} ${endpoint}`,
    duration: durationMs,
    success,
    responseCode: statusCode || 0,
    type: "HTTP",
    target: new URL(endpoint, API_URL).host,
    data: endpoint,
  });

  // Also track as custom event for easier querying
  trackEvent("api_call", {
    method,
    endpoint,
    duration_ms: durationMs.toFixed(2),
    success: String(success),
    status_code: String(statusCode || 0),
  });
}

/**
 * Client-side API hook for authenticated mutations.
 * 
 * Note: Read operations (getPhasesWithProgress, getDashboard, etc.) are handled
 * server-side in api.ts. This hook is only for client-side mutations that need
 * to be called from event handlers.
 */
export function useApi() {
  const { getToken } = useAuth();

  async function fetchWithAuth(url: string, options: RequestInit = {}) {
    const startTime = performance.now();
    const token = await getToken();
    
    let response: Response | null = null;
    let success = false;
    
    try {
      response = await fetch(url, {
        ...options,
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
          ...options.headers,
        },
      });

      success = response.ok;
      
      if (!response.ok) {
        throw new Error(`API error: ${response.status}`);
      }

      return response.json();
    } finally {
      const durationMs = performance.now() - startTime;
      const endpoint = new URL(url).pathname;
      
      // Extract server-side duration from header if available
      const serverDuration = response?.headers.get("X-Request-Duration-Ms");
      
      trackApiCall(
        options.method || "GET",
        endpoint,
        durationMs,
        success,
        response?.status
      );
      
      // Log slow requests to console in development
      if (process.env.NODE_ENV === "development" && durationMs > 500) {
        console.warn(
          `Slow API call: ${options.method || "GET"} ${endpoint} took ${durationMs.toFixed(0)}ms` +
          (serverDuration ? ` (server: ${serverDuration}ms)` : "")
        );
      }
    }
  }

  return {
    /**
     * Toggle a checklist item's completion status.
     */
    async toggleChecklistItem(itemId: string): Promise<{ is_completed: boolean }> {
      return fetchWithAuth(`${API_URL}/api/checklist/${itemId}/toggle`, {
        method: "POST",
      });
    },
  };
}
