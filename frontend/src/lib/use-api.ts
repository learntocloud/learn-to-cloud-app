"use client";

import { useAuth } from "@clerk/nextjs";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

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
    const token = await getToken();
    
    const res = await fetch(url, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...options.headers,
      },
    });

    if (!res.ok) {
      throw new Error(`API error: ${res.status}`);
    }

    return res.json();
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
