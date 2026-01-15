"use client";

import { useEffect } from "react";
import { initAppInsights, trackException } from "@/lib/app-insights";

export function AppInsightsProvider({ children }: { children: React.ReactNode }) {
  useEffect(() => {
    // Initialize Application Insights asynchronously (non-blocking)
    // This defers loading the ~100KB SDK until after hydration
    initAppInsights().catch(console.error);

    // Global error handler for uncaught errors
    const handleError = (event: ErrorEvent) => {
      trackException(event.error || new Error(event.message), {
        source: "window.onerror",
        filename: event.filename || "unknown",
        lineno: String(event.lineno || 0),
        colno: String(event.colno || 0),
      });
    };

    // Global handler for unhandled promise rejections
    const handleRejection = (event: PromiseRejectionEvent) => {
      const error = event.reason instanceof Error 
        ? event.reason 
        : new Error(String(event.reason));
      trackException(error, { source: "unhandledrejection" });
    };

    window.addEventListener("error", handleError);
    window.addEventListener("unhandledrejection", handleRejection);

    return () => {
      window.removeEventListener("error", handleError);
      window.removeEventListener("unhandledrejection", handleRejection);
    };
  }, []);

  return <>{children}</>;
}
