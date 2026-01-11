import { auth } from "@clerk/nextjs/server";
import type {
  PhaseProgress,
  PhaseWithProgress,
  PhaseDetailWithProgress,
  TopicWithProgress,
  ChecklistItemWithProgress,
  TopicChecklistItemWithProgress,
  DashboardResponse,
  PhaseGitHubRequirements,
  GitHubValidationResult,
} from "./types";
import { getAllPhases, getPhaseBySlug as getPhaseBySlugFromContent, getTopicBySlug as getTopicBySlugFromContent } from "./content";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function getAuthHeaders(): Promise<HeadersInit> {
  const { getToken } = await auth();
  const token = await getToken();
  
  return {
    "Content-Type": "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

// ============ Progress API Types ============

interface ProgressItem {
  checklist_item_id: string;
  is_completed: boolean;
  completed_at: string | null;
}

interface UserProgressResponse {
  user_id: string;
  items: ProgressItem[];
}

interface UserInfo {
  id: string;
  email: string;
  first_name: string | null;
  last_name: string | null;
  avatar_url: string | null;
  github_username: string | null;
  created_at: string;
}

// ============ Progress API Calls ============

export async function getUserProgress(): Promise<UserProgressResponse> {
  const headers = await getAuthHeaders();
  
  const res = await fetch(`${API_URL}/api/user/progress`, {
    headers,
    cache: "no-store",
  });
  
  if (!res.ok) {
    const errorText = await res.text().catch(() => "Unknown error");
    throw new Error(`Failed to fetch progress: ${res.status} ${res.statusText} - ${errorText}`);
  }
  
  return res.json();
}

export async function getUserInfo(): Promise<UserInfo> {
  const headers = await getAuthHeaders();
  
  const res = await fetch(`${API_URL}/api/user/me`, {
    headers,
    cache: "no-store",
  });
  
  if (!res.ok) {
    throw new Error("Failed to fetch user info");
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

// ============ GitHub Submission API Calls ============

export async function getPhaseGitHubRequirements(phaseId: number): Promise<PhaseGitHubRequirements> {
  const headers = await getAuthHeaders();
  
  const res = await fetch(`${API_URL}/api/github/requirements/${phaseId}`, {
    headers,
    cache: "no-store",
  });
  
  if (!res.ok) {
    // Return empty requirements instead of throwing
    return {
      phase_id: phaseId,
      requirements: [],
      submissions: [],
      all_validated: true,
    };
  }
  
  return res.json();
}

export async function submitGitHubUrl(
  requirementId: string,
  submittedUrl: string
): Promise<GitHubValidationResult> {
  const headers = await getAuthHeaders();
  
  const res = await fetch(`${API_URL}/api/github/submit`, {
    method: "POST",
    headers,
    body: JSON.stringify({
      requirement_id: requirementId,
      submitted_url: submittedUrl,
    }),
  });
  
  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: "Failed to submit GitHub URL" }));
    throw new Error(error.detail || "Failed to submit GitHub URL");
  }
  
  return res.json();
}

// ============ Helper Functions to Merge Content + Progress ============

function calculatePhaseProgress(
  phaseId: number,
  topicChecklists: { id: string }[][],
  progressItems: ProgressItem[]
): PhaseProgress {
  const allItemIds = topicChecklists.flat().map(c => c.id);
  
  const completedCount = allItemIds.filter(id => 
    progressItems.some(p => p.checklist_item_id === id && p.is_completed)
  ).length;
  
  const total = allItemIds.length;
  const percentage = total > 0 ? (completedCount / total) * 100 : 0;
  
  let status: 'not_started' | 'in_progress' | 'completed' = 'not_started';
  if (completedCount === total && total > 0) {
    status = 'completed';
  } else if (completedCount > 0) {
    status = 'in_progress';
  }
  
  return {
    phase_id: phaseId,
    checklist_completed: completedCount,
    checklist_total: total,
    percentage: Math.round(percentage * 10) / 10,
    status,
  };
}

// ============ Combined Content + Progress Functions ============

export async function getPhasesWithProgress(): Promise<PhaseWithProgress[]> {
  const phases = getAllPhases();
  const { items: progressItems } = await getUserProgress();
  
  // Fetch GitHub requirements for all phases that have them
  const githubRequirementsMap = new Map<number, PhaseGitHubRequirements>();
  for (const phase of phases) {
    try {
      const requirements = await getPhaseGitHubRequirements(phase.id);
      if (requirements.requirements.length > 0) {
        githubRequirementsMap.set(phase.id, requirements);
      }
    } catch {
      // Ignore errors - phase might not have requirements
    }
  }
  
  // First pass: calculate progress for all phases
  const phasesWithProgress = phases.map(phase => {
    const progress = calculatePhaseProgress(
      phase.id,
      phase.topics.map(t => t.checklist),
      progressItems
    );
    
    return {
      ...phase,
      progress,
      isLocked: false, // Will be calculated in second pass
    };
  });
  
  // Second pass: determine locked status based on previous phase completion AND GitHub requirements
  // Phase 0 is always unlocked, subsequent phases require previous phase to be completed
  for (let i = 1; i < phasesWithProgress.length; i++) {
    const previousPhase = phasesWithProgress[i - 1];
    const isPreviousCompleted = previousPhase.progress?.status === 'completed';
    
    // Also check if GitHub requirements are validated for the previous phase
    const previousGithubReqs = githubRequirementsMap.get(previousPhase.id);
    const areGithubReqsValidated = !previousGithubReqs || previousGithubReqs.all_validated;
    
    phasesWithProgress[i].isLocked = !isPreviousCompleted || !areGithubReqsValidated;
  }
  
  return phasesWithProgress;
}

export async function getPhaseWithProgressBySlug(slug: string): Promise<(PhaseDetailWithProgress & { isLocked: boolean }) | null> {
  const phase = getPhaseBySlugFromContent(slug);
  if (!phase) return null;
  
  const { items: progressItems } = await getUserProgress();
  
  // Check if this phase is locked (previous phase must be completed + GitHub requirements validated)
  let isLocked = false;
  if (phase.id > 0) {
    const phases = getAllPhases();
    const previousPhase = phases.find(p => p.id === phase.id - 1);
    if (previousPhase) {
      const previousProgress = calculatePhaseProgress(
        previousPhase.id,
        previousPhase.topics.map(t => t.checklist),
        progressItems
      );
      const checklistNotCompleted = previousProgress.status !== 'completed';
      
      // Also check GitHub requirements for the previous phase
      let githubReqsNotValidated = false;
      try {
        const githubReqs = await getPhaseGitHubRequirements(previousPhase.id);
        if (githubReqs.requirements.length > 0) {
          githubReqsNotValidated = !githubReqs.all_validated;
        }
      } catch {
        // Ignore errors
      }
      
      isLocked = checklistNotCompleted || githubReqsNotValidated;
    }
  }
  
  // Add progress to topics
  const topics: TopicWithProgress[] = phase.topics.map(topic => {
    const topicChecklist: TopicChecklistItemWithProgress[] = topic.checklist.map(item => {
      const progressItem = progressItems.find(p => p.checklist_item_id === item.id);
      return {
        ...item,
        is_completed: progressItem?.is_completed ?? false,
        completed_at: progressItem?.completed_at ?? null,
      };
    });
    
    const itemsCompleted = topicChecklist.filter(c => c.is_completed).length;
    
    return {
      ...topic,
      checklist: topicChecklist,
      items_completed: itemsCompleted,
      items_total: topicChecklist.length,
    };
  });
  
  const progress = calculatePhaseProgress(
    phase.id,
    phase.topics.map(t => t.checklist),
    progressItems
  );
  
  return {
    ...phase,
    topics,
    progress,
    isLocked,
  };
}

export async function getTopicWithProgressBySlug(phaseSlug: string, topicSlug: string): Promise<(TopicWithProgress & { isLocked: boolean }) | null> {
  const phase = getPhaseBySlugFromContent(phaseSlug);
  if (!phase) return null;
  
  const topic = getTopicBySlugFromContent(phaseSlug, topicSlug);
  if (!topic) return null;
  
  const { items: progressItems } = await getUserProgress();
  
  // Check if this phase is locked (previous phase must be completed + GitHub requirements validated)
  let isLocked = false;
  if (phase.id > 0) {
    const phases = getAllPhases();
    const previousPhase = phases.find(p => p.id === phase.id - 1);
    if (previousPhase) {
      const previousProgress = calculatePhaseProgress(
        previousPhase.id,
        previousPhase.topics.map(t => t.checklist),
        progressItems
      );
      const checklistNotCompleted = previousProgress.status !== 'completed';
      
      // Also check GitHub requirements for the previous phase
      let githubReqsNotValidated = false;
      try {
        const githubReqs = await getPhaseGitHubRequirements(previousPhase.id);
        if (githubReqs.requirements.length > 0) {
          githubReqsNotValidated = !githubReqs.all_validated;
        }
      } catch {
        // Ignore errors
      }
      
      isLocked = checklistNotCompleted || githubReqsNotValidated;
    }
  }
  
  const checklist: TopicChecklistItemWithProgress[] = topic.checklist.map(item => {
    const progressItem = progressItems.find(p => p.checklist_item_id === item.id);
    return {
      ...item,
      is_completed: progressItem?.is_completed ?? false,
      completed_at: progressItem?.completed_at ?? null,
    };
  });
  
  const itemsCompleted = checklist.filter(c => c.is_completed).length;
  
  return {
    ...topic,
    checklist,
    items_completed: itemsCompleted,
    items_total: checklist.length,
    isLocked,
  };
}

export async function getDashboard(): Promise<DashboardResponse> {
  const [userInfo, phasesWithProgress] = await Promise.all([
    getUserInfo(),
    getPhasesWithProgress(),
  ]);
  
  const totalItems = phasesWithProgress.reduce(
    (sum, p) => sum + (p.progress?.checklist_total ?? 0), 
    0
  );
  const totalCompleted = phasesWithProgress.reduce(
    (sum, p) => sum + (p.progress?.checklist_completed ?? 0), 
    0
  );
  const overallProgress = totalItems > 0 ? (totalCompleted / totalItems) * 100 : 0;
  
  // Find current phase (first in-progress, or first not-started)
  let currentPhase: number | null = null;
  const inProgress = phasesWithProgress.find(p => p.progress?.status === 'in_progress');
  if (inProgress) {
    currentPhase = inProgress.id;
  } else {
    const notStarted = phasesWithProgress.find(p => p.progress?.status === 'not_started');
    if (notStarted) {
      currentPhase = notStarted.id;
    }
  }
  
  return {
    user: userInfo,
    phases: phasesWithProgress,
    overall_progress: Math.round(overallProgress * 10) / 10,
    total_completed: totalCompleted,
    total_items: totalItems,
    current_phase: currentPhase,
  };
}
