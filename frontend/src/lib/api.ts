import { auth } from "@clerk/nextjs/server";
import type {
  PhaseProgress,
  PhaseWithProgress,
  PhaseDetailWithProgress,
  TopicWithProgress,
  DashboardResponse,
  PhaseGitHubRequirements,
  TopicQuestionsStatus,
  StreakResponse,
  ActivityHeatmapResponse,
  PublicProfileResponse,
  CertificateEligibility,
  Certificate,
  CertificateVerifyResponse,
  UserCertificates,
} from "./types";
import { getAllPhases, getPhaseBySlug as getPhaseBySlugFromContent, getTopicBySlug as getTopicBySlugFromContent } from "./content";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function getAuthHeaders(): Promise<HeadersInit> {
  const { getToken, userId } = await auth();
  const token = await getToken();
  
  // Debug: log auth state on server
  if (process.env.NODE_ENV === 'development') {
    console.log(`[API Auth] userId: ${userId}, hasToken: ${!!token}`);
  }
  
  return {
    "Content-Type": "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

// ============ Progress API Types ============

interface UserInfo {
  id: string;
  email: string;
  first_name: string | null;
  last_name: string | null;
  avatar_url: string | null;
  github_username: string | null;
  is_admin: boolean;
  created_at: string;
}

// ============ User Info API Call ============

export async function getUserInfo(): Promise<UserInfo> {
  const headers = await getAuthHeaders();
  
  const res = await fetch(`${API_URL}/api/user/me`, {
    headers,
    cache: "no-store",
  });
  
  if (!res.ok) {
    const errorText = await res.text().catch(() => "Unknown error");
    throw new Error(`Failed to fetch user info: ${res.status} ${res.statusText} - ${errorText}`);
  }
  
  return res.json();
}

// ============ Streak & Activity API Calls ============

export async function getStreak(): Promise<StreakResponse> {
  const headers = await getAuthHeaders();
  
  const res = await fetch(`${API_URL}/api/activity/streak`, {
    headers,
    cache: "no-store",
  });
  
  if (!res.ok) {
    return { 
      current_streak: 0, 
      longest_streak: 0, 
      total_activity_days: 0,
      last_activity_date: null,
      streak_alive: false 
    };
  }
  
  return res.json();
}

export async function getActivityHeatmap(days: number = 365): Promise<ActivityHeatmapResponse> {
  const headers = await getAuthHeaders();
  
  const res = await fetch(`${API_URL}/api/activity/heatmap?days=${days}`, {
    headers,
    cache: "no-store",
  });
  
  if (!res.ok) {
    const today = new Date().toISOString().split('T')[0];
    const startDate = new Date(Date.now() - days * 24 * 60 * 60 * 1000).toISOString().split('T')[0];
    return { days: [], start_date: startDate, end_date: today, total_activities: 0 };
  }
  
  return res.json();
}

// ============ Badge API Calls ============

export async function getCurrentUserBadges(): Promise<{ id: string; name: string; icon: string }[]> {
  // Get user info first to get github_username
  const userInfo = await getUserInfo();
  if (!userInfo?.github_username) {
    return [];
  }
  
  // Then fetch profile which includes badges
  const profile = await getPublicProfile(userInfo.github_username);
  if (!profile?.badges) {
    return [];
  }
  
  return profile.badges.map(b => ({ id: b.id, name: b.name, icon: b.icon }));
}

// ============ Public Profile API Calls ============

export async function getPublicProfile(username: string): Promise<PublicProfileResponse | null> {
  const headers = await getAuthHeaders();
  
  const res = await fetch(`${API_URL}/api/user/profile/${encodeURIComponent(username)}`, {
    headers,
    cache: "no-store",
  });
  
  if (!res.ok) {
    // Return null for 404/403 instead of throwing
    if (res.status === 404 || res.status === 403) {
      return null;
    }
    throw new Error(`Failed to fetch profile: ${res.status}`);
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
  topics: { questions?: { id: string }[]; learning_steps: { order: number }[]; id: string }[],
  questionsStatusMap: Record<string, TopicQuestionsStatus>,
  stepsStatusMap: Record<string, number[]>,
  githubValidated: boolean = true,  // Whether all GitHub requirements for this phase are validated
  handsOnRequiredCount: number = 0,  // Number of hands-on requirements for this phase
  handsOnValidatedCount: number = 0  // Number of validated hands-on submissions
): PhaseProgress {
  // Count both questions and steps for progress calculation
  let totalItems = 0;
  let completedItems = 0;
  
  for (const topic of topics) {
    // Count steps
    const topicStepCount = topic.learning_steps?.length ?? 0;
    totalItems += topicStepCount;
    const completedSteps = stepsStatusMap[topic.id] ?? [];
    completedItems += completedSteps.length;
    
    // Count questions
    const topicQuestionCount = topic.questions?.length ?? 0;
    totalItems += topicQuestionCount;
    const status = questionsStatusMap[topic.id];
    completedItems += status?.passed_questions ?? 0;
  }
  
  // Include each hands-on requirement individually in the progress calculation
  // Per SKILL.md: Phase Progress = (Steps + Questions + Hands-on Validated) / (Total Steps + Total Questions + Total Hands-on)
  if (handsOnRequiredCount > 0) {
    totalItems += handsOnRequiredCount;
    completedItems += handsOnValidatedCount;
  }
  
  const percentage = totalItems > 0 ? (completedItems / totalItems) * 100 : 0;
  
  // Status logic:
  // - "completed" only if all steps + questions done AND GitHub validated (if required)
  // - "in_progress" if any progress made
  // - "not_started" otherwise
  let status: 'not_started' | 'in_progress' | 'completed' = 'not_started';
  const allDone = completedItems === totalItems && totalItems > 0;
  if (allDone) {
    status = 'completed';
  } else if (completedItems > 0) {
    status = 'in_progress';
  }
  
  // Note: We keep questions_passed/questions_total for backward compatibility
  // but the percentage now includes steps, questions, AND GitHub verification
  let totalQuestions = 0;
  let passedQuestions = 0;
  for (const topic of topics) {
    const topicQuestionCount = topic.questions?.length ?? 0;
    totalQuestions += topicQuestionCount;
    const status = questionsStatusMap[topic.id];
    passedQuestions += status?.passed_questions ?? 0;
  }
  
  return {
    phase_id: phaseId,
    questions_passed: passedQuestions,
    questions_total: totalQuestions,
    percentage: Math.round(percentage * 10) / 10,
    status,
  };
}

// ============ Combined Content + Progress Functions ============

export async function getPhasesWithProgress(): Promise<PhaseWithProgress[]> {
  const phases = getAllPhases();
  
  // Fetch GitHub requirements, questions status, steps status, AND user info in parallel
  const [githubRequirementsMap, questionsStatusMap, stepsStatusMap, userInfo] = await Promise.all([
    getAllGitHubRequirements(),
    getAllQuestionsStatus(),
    getAllStepsStatus(),
    getUserInfo().catch(() => null), // Don't fail if user info unavailable
  ]);
  
  // Admins bypass all content locks
  const isAdmin = userInfo?.is_admin ?? false;
  
  // First pass: calculate progress for all phases (steps + questions + GitHub)
  const phasesWithProgress = phases.map(phase => {
    // Get hands-on requirements and count validated submissions for this phase
    const githubReqs = githubRequirementsMap.get(phase.id);
    const handsOnRequiredCount = githubReqs?.requirements.length ?? 0;
    const handsOnValidatedCount = githubReqs?.submissions.filter(s => s.is_validated).length ?? 0;
    const githubValidated = handsOnRequiredCount === 0 || handsOnValidatedCount >= handsOnRequiredCount;
    
    const progress = calculatePhaseProgress(
      phase.id,
      phase.topics,
      questionsStatusMap,
      stepsStatusMap,
      githubValidated,
      handsOnRequiredCount,
      handsOnValidatedCount
    );
    
    return {
      ...phase,
      progress,
      isLocked: false, // Will be calculated in second pass
    };
  });
  
  // Second pass: determine locked status based on previous phase completion
  // Phase 0 is always unlocked, subsequent phases require previous phase to be "completed"
  // (which now includes GitHub validation)
  // Admins bypass all locks
  if (!isAdmin) {
    for (let i = 1; i < phasesWithProgress.length; i++) {
      const previousPhase = phasesWithProgress[i - 1];
      const isPreviousCompleted = previousPhase.progress?.status === 'completed';
      
      // Lock cascades: if previous phase is locked OR not completed, this phase is locked
      phasesWithProgress[i].isLocked = previousPhase.isLocked || !isPreviousCompleted;
    }
  }
  
  return phasesWithProgress;
}

// Helper to check if a phase is locked based on previous phases' completion
// A phase is locked if ANY previous phase is not "completed" (steps + questions + GitHub)
async function checkPhaseLocked(
  phaseId: number,
  githubRequirementsMap?: Map<number, PhaseGitHubRequirements>,
  questionsStatusMap?: Record<string, TopicQuestionsStatus>,
  stepsStatusMap?: Record<string, number[]>,
  isAdmin?: boolean
): Promise<boolean> {
  // Admins bypass all content locks
  if (isAdmin) return false;
  
  if (phaseId === 0) return false;
  
  const phases = getAllPhases();
  const githubReqs = githubRequirementsMap ?? await getAllGitHubRequirements();
  const questionsStatus = questionsStatusMap ?? await getAllQuestionsStatus();
  const stepsStatus = stepsStatusMap ?? await getAllStepsStatus();
  
  // Check all previous phases are completed
  for (let i = 0; i < phaseId; i++) {
    const prevPhase = phases.find(p => p.id === i);
    if (!prevPhase) continue;
    
    // Get hands-on requirements and count validated submissions for this phase
    const prevGithubReqs = githubReqs.get(prevPhase.id);
    const handsOnRequiredCount = prevGithubReqs?.requirements.length ?? 0;
    const handsOnValidatedCount = prevGithubReqs?.submissions.filter(s => s.is_validated).length ?? 0;
    const githubValidated = handsOnRequiredCount === 0 || handsOnValidatedCount >= handsOnRequiredCount;
    
    const prevProgress = calculatePhaseProgress(
      prevPhase.id,
      prevPhase.topics,
      questionsStatus,
      stepsStatus,
      githubValidated,
      handsOnRequiredCount,
      handsOnValidatedCount
    );
    
    // If previous phase is not completed, this phase is locked
    if (prevProgress.status !== 'completed') {
      return true;
    }
  }
  
  return false;
}

export async function getPhaseWithProgressBySlug(slug: string): Promise<(PhaseDetailWithProgress & { isLocked: boolean }) | null> {
  const phase = getPhaseBySlugFromContent(slug);
  if (!phase) return null;
  
  // Fetch GitHub requirements, questions status, steps status, AND user info in parallel
  const [githubRequirementsMap, questionsStatusMap, stepsStatusMap, userInfo] = await Promise.all([
    getAllGitHubRequirements(),
    getAllQuestionsStatus(),
    getAllStepsStatus(),
    getUserInfo().catch(() => null), // Don't fail if user info unavailable
  ]);
  
  // Admins bypass all content locks
  const isAdmin = userInfo?.is_admin ?? false;
  
  const isLocked = await checkPhaseLocked(phase.id, githubRequirementsMap, questionsStatusMap, stepsStatusMap, isAdmin);
  
  // Add progress to topics (steps + questions)
  const topics: TopicWithProgress[] = phase.topics.map(topic => {
    const questionsStatus = questionsStatusMap[topic.id];
    const questionCount = topic.questions?.length ?? 0;
    const questionsCompleted = questionsStatus?.passed_questions ?? 0;
    const stepCount = topic.learning_steps?.length ?? 0;
    const completedSteps = stepsStatusMap[topic.id] ?? [];
    
    return {
      ...topic,
      questions_passed: questionsCompleted,
      questions_total: questionCount,
      steps_completed: completedSteps.length,
      steps_total: stepCount,
    };
  });
  
  // Include GitHub validation in phase progress
  const githubReqs = githubRequirementsMap.get(phase.id);
  const handsOnRequiredCount = githubReqs?.requirements.length ?? 0;
  const handsOnValidatedCount = githubReqs?.submissions.filter(s => s.is_validated).length ?? 0;
  const githubValidated = handsOnRequiredCount === 0 || handsOnValidatedCount >= handsOnRequiredCount;
  
  const progress = calculatePhaseProgress(
    phase.id,
    phase.topics,
    questionsStatusMap,
    stepsStatusMap,
    githubValidated,
    handsOnRequiredCount,
    handsOnValidatedCount
  );
  
  return {
    ...phase,
    topics,
    progress,
    isLocked,
  };
}

export async function getTopicWithProgressBySlug(phaseSlug: string, topicSlug: string): Promise<(TopicWithProgress & { isLocked: boolean; isTopicLocked: boolean; previousTopicName?: string }) | null> {
  const phase = getPhaseBySlugFromContent(phaseSlug);
  if (!phase) return null;
  
  const topic = getTopicBySlugFromContent(phaseSlug, topicSlug);
  if (!topic) return null;
  
  // Fetch GitHub requirements, questions status, steps status, AND user info in parallel
  const [githubRequirementsMap, questionsStatusMap, stepsStatusMap, userInfo] = await Promise.all([
    getAllGitHubRequirements(),
    getAllQuestionsStatus(),
    getAllStepsStatus(),
    getUserInfo().catch(() => null), // Don't fail if user info unavailable
  ]);
  
  // Admins bypass all content locks
  const isAdmin = userInfo?.is_admin ?? false;
  
  const isLocked = await checkPhaseLocked(phase.id, githubRequirementsMap, questionsStatusMap, stepsStatusMap, isAdmin);
  
  // Calculate topic-level locking: previous topic must have all steps AND questions complete
  // Admins bypass topic-level locks too
  const topicIndex = phase.topics.findIndex(t => t.slug === topicSlug);
  let isTopicLocked = false;
  let previousTopicName: string | undefined;
  
  if (topicIndex > 0 && !isAdmin) {
    const previousTopic = phase.topics[topicIndex - 1];
    previousTopicName = previousTopic.name;
    
    // Check if previous topic's steps are all complete
    const prevStepCount = previousTopic.learning_steps?.length ?? 0;
    const prevCompletedSteps = stepsStatusMap[previousTopic.id] ?? [];
    const areStepsComplete = prevStepCount === 0 || prevCompletedSteps.length >= prevStepCount;
    
    // Check if previous topic's questions are all passed
    const prevQuestionsStatus = questionsStatusMap[previousTopic.id];
    const prevQuestionCount = previousTopic.questions?.length ?? 0;
    const areQuestionsComplete = prevQuestionCount === 0 || (prevQuestionsStatus?.all_passed ?? false);
    
    isTopicLocked = !areStepsComplete || !areQuestionsComplete;
  }
  
  const questionsStatus = questionsStatusMap[topic.id];
  const questionCount = topic.questions?.length ?? 0;
  const questionsCompleted = questionsStatus?.passed_questions ?? 0;
  const stepCount = topic.learning_steps?.length ?? 0;
  const completedSteps = stepsStatusMap[topic.id] ?? [];
  
  return {
    ...topic,
    questions_passed: questionsCompleted,
    questions_total: questionCount,
    steps_completed: completedSteps.length,
    steps_total: stepCount,
    isLocked,
    isTopicLocked,
    previousTopicName,
  };
}

export async function getDashboard(): Promise<DashboardResponse> {
  const [userInfo, phasesWithProgress] = await Promise.all([
    getUserInfo(),
    getPhasesWithProgress(),
  ]);
  
  // Calculate overall progress from phase percentages (which include steps + questions + GitHub)
  const phasesWithContent = phasesWithProgress.filter(p => (p.progress?.percentage ?? 0) >= 0);
  const totalPercentage = phasesWithContent.reduce(
    (sum, p) => sum + (p.progress?.percentage ?? 0), 
    0
  );
  const overallProgress = phasesWithContent.length > 0 
    ? totalPercentage / phasesWithContent.length 
    : 0;
  
  // Simplified progress - just phases (phase complete = steps + questions + GitHub validated)
  const phasesCompleted = phasesWithProgress.filter(p => p.progress?.status === 'completed').length;
  const phasesTotal = phasesWithProgress.length;
  
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
    phases_completed: phasesCompleted,
    phases_total: phasesTotal,
    current_phase: currentPhase,
  };
}

// ============ Questions API Calls ============

export async function getTopicQuestionsStatus(topicId: string): Promise<TopicQuestionsStatus | null> {
  const headers = await getAuthHeaders();
  
  const res = await fetch(`${API_URL}/api/questions/topic/${topicId}/status`, {
    headers,
    cache: "no-store",
  });
  
  if (!res.ok) {
    return null;
  }
  
  return res.json();
}

export async function getAllQuestionsStatus(): Promise<Record<string, TopicQuestionsStatus>> {
  const headers = await getAuthHeaders();
  
  const res = await fetch(`${API_URL}/api/questions/user/all-status`, {
    headers,
    cache: "no-store",
  });
  
  if (!res.ok) {
    return {};
  }
  
  return res.json();
}

export async function getAllStepsStatus(): Promise<Record<string, number[]>> {
  const headers = await getAuthHeaders();
  
  const res = await fetch(`${API_URL}/api/steps/user/all-status`, {
    headers,
    cache: "no-store",
  });
  
  if (!res.ok) {
    return {};
  }
  
  return res.json();
}

// ============ Certificate API Calls ============

export async function getCertificateEligibility(certificateType: string): Promise<CertificateEligibility> {
  const headers = await getAuthHeaders();
  
  const res = await fetch(`${API_URL}/api/certificates/eligibility/${encodeURIComponent(certificateType)}`, {
    headers,
    cache: "no-store",
  });
  
  if (!res.ok) {
    throw new Error(`Failed to check eligibility: ${res.status}`);
  }
  
  return res.json();
}

export async function getUserCertificates(): Promise<UserCertificates> {
  const headers = await getAuthHeaders();
  
  const res = await fetch(`${API_URL}/api/certificates`, {
    headers,
    cache: "no-store",
  });
  
  if (!res.ok) {
    return { certificates: [], full_completion_eligible: false };
  }
  
  return res.json();
}

export async function getCertificate(certificateId: number): Promise<Certificate | null> {
  const headers = await getAuthHeaders();
  
  const res = await fetch(`${API_URL}/api/certificates/${certificateId}`, {
    headers,
    cache: "no-store",
  });
  
  if (!res.ok) {
    return null;
  }
  
  return res.json();
}

export async function verifyCertificate(verificationCode: string): Promise<CertificateVerifyResponse> {
  // Public endpoint - no auth required
  const res = await fetch(`${API_URL}/api/certificates/verify/${encodeURIComponent(verificationCode)}`, {
    headers: { "Content-Type": "application/json" },
    cache: "no-store",
  });
  
  if (!res.ok) {
    return {
      is_valid: false,
      certificate: null,
      message: "Failed to verify certificate",
    };
  }
  
  return res.json();
}

export function getCertificateSvgUrl(certificateId: number): string {
  return `${API_URL}/api/certificates/${certificateId}/svg`;
}

export function getCertificatePdfUrl(certificateId: number): string {
  return `${API_URL}/api/certificates/${certificateId}/pdf`;
}

export function getVerifiedCertificateSvgUrl(verificationCode: string): string {
  return `${API_URL}/api/certificates/verify/${encodeURIComponent(verificationCode)}/svg`;
}

export function getVerifiedCertificatePdfUrl(verificationCode: string): string {
  return `${API_URL}/api/certificates/verify/${encodeURIComponent(verificationCode)}/pdf`;
}
