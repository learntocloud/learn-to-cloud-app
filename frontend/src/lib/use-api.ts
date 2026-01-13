"use client";

import { useAuth } from "@clerk/nextjs";
import { trackEvent, getAppInsights } from "./app-insights";
import type { QuestionSubmitResponse, ReflectionResponse, StreakResponse, LatestGreetingResponse, TopicQuestionsStatus } from "./types";

// In dev containers/Codespaces, use same-origin proxy (Next.js rewrites /api/* to backend)
// In production, use the explicit API URL
const API_URL = process.env.NEXT_PUBLIC_API_URL || "";

// Check if we're using the proxy (empty or localhost URL)
const isUsingProxy = !API_URL || API_URL.includes('localhost') || API_URL.includes('127.0.0.1');

// User info response type
export interface UserInfo {
  id: string;
  email: string;
  first_name: string | null;
  last_name: string | null;
  avatar_url: string | null;
  github_username: string | null;
  created_at: string;
}

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
    target: isUsingProxy ? window.location.host : new URL(API_URL).host,
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
      // Extract pathname safely - for relative URLs, the url itself is the path
      const endpoint = url.startsWith('/') ? url.split('?')[0] : new URL(url).pathname;
      
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
      // Use relative URL for proxy in dev containers, absolute URL in production
      const url = isUsingProxy 
        ? `/api/checklist/${itemId}/toggle`
        : `${API_URL}/api/checklist/${itemId}/toggle`;
      return fetchWithAuth(url, {
        method: "POST",
      });
    },

    /**
     * Submit an answer to a knowledge question for LLM grading.
     */
    async submitQuestionAnswer(
      topicId: string,
      questionId: string,
      questionPrompt: string,
      expectedConcepts: string[],
      topicName: string,
      userAnswer: string
    ): Promise<QuestionSubmitResponse> {
      const url = isUsingProxy
        ? `/api/questions/submit`
        : `${API_URL}/api/questions/submit`;
      return fetchWithAuth(url, {
        method: "POST",
        body: JSON.stringify({
          topic_id: topicId,
          question_id: questionId,
          question_prompt: questionPrompt,
          expected_concepts: expectedConcepts,
          topic_name: topicName,
          user_answer: userAnswer,
        }),
      });
    },

    /**
     * Submit a daily reflection.
     */
    async submitReflection(reflectionText: string): Promise<ReflectionResponse> {
      const url = isUsingProxy
        ? `/api/reflections`
        : `${API_URL}/api/reflections`;
      return fetchWithAuth(url, {
        method: "POST",
        body: JSON.stringify({
          reflection_text: reflectionText,
        }),
      });
    },

    /**
     * Get today's reflection if one exists.
     */
    async getTodayReflection(): Promise<ReflectionResponse | null> {
      const url = isUsingProxy
        ? `/api/reflections/today`
        : `${API_URL}/api/reflections/today`;
      try {
        return await fetchWithAuth(url, {
          method: "GET",
        });
      } catch {
        // Returns null if no reflection exists for today
        return null;
      }
    },

    /**
     * Get the latest AI-generated greeting from reflection.
     */
    async getLatestGreeting(): Promise<LatestGreetingResponse> {
      const url = isUsingProxy
        ? `/api/reflections/latest`
        : `${API_URL}/api/reflections/latest`;
      return fetchWithAuth(url, {
        method: "GET",
      });
    },

    /**
     * Get the user's current streak information.
     */
    async getStreak(): Promise<StreakResponse> {
      const url = isUsingProxy
        ? `/api/activity/streak`
        : `${API_URL}/api/activity/streak`;
      return fetchWithAuth(url, {
        method: "GET",
      });
    },

    /**
     * Get the status of all questions for a topic.
     */
    async getTopicQuestionsStatus(topicId: string): Promise<TopicQuestionsStatus> {
      const url = isUsingProxy
        ? `/api/questions/topic/${topicId}/status`
        : `${API_URL}/api/questions/topic/${topicId}/status`;
      return fetchWithAuth(url, {
        method: "GET",
      });
    },

    /**
     * Get current user info including github_username.
     */
    async getUserInfo(): Promise<UserInfo> {
      const url = isUsingProxy
        ? `/api/user/me`
        : `${API_URL}/api/user/me`;
      return fetchWithAuth(url, {
        method: "GET",
      });
    },
  };
}
