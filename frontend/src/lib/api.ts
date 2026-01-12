import { auth } from "@clerk/nextjs/server";
import type {
  PhaseProgress,
  PhaseWithProgress,
  PhaseDetailWithProgress,
  TopicWithProgress,
  TopicChecklistItemWithProgress,
  DashboardResponse,
  PhaseGitHubRequirements,
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
      has_requirements: false,
      all_validated: true,
    };
  }
  
  return res.json();
}

// Bulk endpoint - fetches ALL phase requirements in a single call
interface AllPhasesGitHubRequirements {
  phases: PhaseGitHubRequirements[];
}

export async function getAllGitHubRequirements(): Promise<Map<number, PhaseGitHubRequirements>> {
  const headers = await getAuthHeaders();
  
  const res = await fetch(`${API_URL}/api/github/requirements`, {
    headers,
    cache: "no-store",
  });
  
  if (!res.ok) {
    return new Map();
  }
  
  const data: AllPhasesGitHubRequirements = await res.json();
  const map = new Map<number, PhaseGitHubRequirements>();
  for (const phase of data.phases) {
    map.set(phase.phase_id, phase);
  }
  return map;
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
  
  // Fetch user progress AND GitHub requirements in parallel (2 API calls instead of 7+)
  const [{ items: progressItems }, githubRequirementsMap] = await Promise.all([
    getUserProgress(),
    getAllGitHubRequirements(),
  ]);
  
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
    
    // Lock cascades: if previous phase is locked OR not completed, this phase is locked
    phasesWithProgress[i].isLocked = previousPhase.isLocked || !isPreviousCompleted || !areGithubReqsValidated;
  }
  
  return phasesWithProgress;
}

// Helper to check if a phase is locked based on previous phases' progress and GitHub requirements
async function checkPhaseLocked(
  phaseId: number,
  progressItems: ProgressItem[],
  githubRequirementsMap?: Map<number, PhaseGitHubRequirements>
): Promise<boolean> {
  if (phaseId === 0) return false;
  
  const phases = getAllPhases();
  const githubReqs = githubRequirementsMap ?? await getAllGitHubRequirements();
  
  for (let i = 0; i < phaseId; i++) {
    const prevPhase = phases.find(p => p.id === i);
    if (!prevPhase) continue;
    
    const prevProgress = calculatePhaseProgress(
      prevPhase.id,
      prevPhase.topics.map(t => t.checklist),
      progressItems
    );
    
    if (prevProgress.status !== 'completed') {
      return true;
    }
    
    const prevGithubReqs = githubReqs.get(prevPhase.id);
    if (prevGithubReqs && prevGithubReqs.has_requirements && !prevGithubReqs.all_validated) {
      return true;
    }
  }
  
  return false;
}

export async function getPhaseWithProgressBySlug(slug: string): Promise<(PhaseDetailWithProgress & { isLocked: boolean }) | null> {
  const phase = getPhaseBySlugFromContent(slug);
  if (!phase) return null;
  
  // Fetch progress and GitHub requirements in parallel (2 API calls instead of N+1)
  const [{ items: progressItems }, githubRequirementsMap] = await Promise.all([
    getUserProgress(),
    getAllGitHubRequirements(),
  ]);
  
  const isLocked = await checkPhaseLocked(phase.id, progressItems, githubRequirementsMap);
  
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
  
  // Fetch progress and GitHub requirements in parallel (2 API calls instead of N+1)
  const [{ items: progressItems }, githubRequirementsMap] = await Promise.all([
    getUserProgress(),
    getAllGitHubRequirements(),
  ]);
  
  const isLocked = await checkPhaseLocked(phase.id, progressItems, githubRequirementsMap);
  
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
