import { auth } from "@clerk/nextjs/server";
import type {
  Phase,
  PhaseWithProgress,
  PhaseDetailWithProgress,
  DashboardResponse,
} from "./types";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function getAuthHeaders(): Promise<HeadersInit> {
  const { getToken } = await auth();
  const token = await getToken();
  
  return {
    "Content-Type": "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

// ============ Public API calls ============

export async function getPhases(): Promise<Phase[]> {
  const res = await fetch(`${API_URL}/api/phases`, {
    next: { revalidate: 3600 }, // Cache for 1 hour
  });
  
  if (!res.ok) {
    throw new Error("Failed to fetch phases");
  }
  
  return res.json();
}

export async function getPhase(phaseId: number): Promise<Phase> {
  const res = await fetch(`${API_URL}/api/phases/${phaseId}`, {
    next: { revalidate: 3600 },
  });
  
  if (!res.ok) {
    throw new Error("Failed to fetch phase");
  }
  
  return res.json();
}

export async function getPhaseBySlug(slug: string): Promise<Phase> {
  const res = await fetch(`${API_URL}/api/p/${slug}`, {
    next: { revalidate: 3600 },
  });
  
  if (!res.ok) {
    throw new Error("Failed to fetch phase");
  }
  
  return res.json();
}

export async function getTopicBySlug(phaseSlug: string, topicSlug: string): Promise<import("./types").Topic> {
  const res = await fetch(`${API_URL}/api/p/${phaseSlug}/${topicSlug}`, {
    next: { revalidate: 3600 },
  });
  
  if (!res.ok) {
    throw new Error("Failed to fetch topic");
  }
  
  return res.json();
}

export async function getTopicWithProgressBySlug(phaseSlug: string, topicSlug: string): Promise<import("./types").TopicWithProgress> {
  const headers = await getAuthHeaders();
  
  const res = await fetch(`${API_URL}/api/user/p/${phaseSlug}/${topicSlug}`, {
    headers,
    cache: "no-store",
  });
  
  if (!res.ok) {
    throw new Error("Failed to fetch topic with progress");
  }
  
  return res.json();
}

// ============ Authenticated API calls ============

export async function getPhasesWithProgress(): Promise<PhaseWithProgress[]> {
  const headers = await getAuthHeaders();
  
  const res = await fetch(`${API_URL}/api/user/phases`, {
    headers,
    cache: "no-store",
  });
  
  if (!res.ok) {
    throw new Error("Failed to fetch phases with progress");
  }
  
  return res.json();
}

export async function getPhaseWithProgress(phaseId: number): Promise<PhaseDetailWithProgress> {
  const headers = await getAuthHeaders();
  
  const res = await fetch(`${API_URL}/api/user/phases/${phaseId}`, {
    headers,
    cache: "no-store",
  });
  
  if (!res.ok) {
    throw new Error("Failed to fetch phase with progress");
  }
  
  return res.json();
}

export async function getPhaseWithProgressBySlug(slug: string): Promise<PhaseDetailWithProgress> {
  const headers = await getAuthHeaders();
  
  const res = await fetch(`${API_URL}/api/user/p/${slug}`, {
    headers,
    cache: "no-store",
  });
  
  if (!res.ok) {
    throw new Error("Failed to fetch phase with progress");
  }
  
  return res.json();
}

export async function getDashboard(): Promise<DashboardResponse> {
  const headers = await getAuthHeaders();
  
  const res = await fetch(`${API_URL}/api/user/dashboard`, {
    headers,
    cache: "no-store",
  });
  
  if (!res.ok) {
    const errorText = await res.text();
    console.error(`Dashboard API error: ${res.status} - ${errorText}`);
    throw new Error(`Failed to fetch dashboard: ${res.status}`);
  }
  
  return res.json();
}

// ============ Client-side API calls (for mutations) ============

export async function toggleChecklistItem(itemId: string): Promise<{ is_completed: boolean }> {
  const res = await fetch(`${API_URL}/api/checklist/${itemId}/toggle`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    credentials: "include",
  });
  
  if (!res.ok) {
    throw new Error("Failed to toggle checklist item");
  }
  
  return res.json();
}
