"use client";

import { useAuth } from "@clerk/nextjs";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

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
    async toggleChecklistItem(itemId: string) {
      return fetchWithAuth(`${API_URL}/api/checklist/${itemId}/toggle`, {
        method: "POST",
      });
    },

    async getDashboard() {
      return fetchWithAuth(`${API_URL}/api/user/dashboard`);
    },

    async getPhaseWithProgress(phaseId: number) {
      return fetchWithAuth(`${API_URL}/api/user/phases/${phaseId}`);
    },
  };
}
