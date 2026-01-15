/**
 * App Insights Provider - placeholder for Azure Application Insights integration.
 * In the real implementation, this would initialize Application Insights and track page views.
 */

import { ReactNode } from 'react';

interface AppInsightsProviderProps {
  children: ReactNode;
}

export function AppInsightsProvider({ children }: AppInsightsProviderProps) {
  // TODO: Initialize Application Insights here if needed
  // For now, just render children
  return <>{children}</>;
}
