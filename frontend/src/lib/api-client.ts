/**
 * API client for Learn to Cloud backend.
 * Uses Clerk for authentication.
 *
 * This is a simple client that calls the API endpoints.
 * All business logic (progress calculation, locking) is handled server-side.
 */

import type {
  QuestionSubmitResponse,
  TopicStepProgress,
  StreakResponse,
  PublicProfileResponse,
  CertificateEligibility,
  Certificate,
  CertificateVerifyResponse,
  UserCertificates,
  GitHubValidationResult,
} from './types';

export type { GitHubValidationResult } from './types';

/**
 * Error thrown when user exceeds max quiz attempts and is locked out.
 */
export class LockoutError extends Error {
  constructor(
    message: string,
    public lockoutUntil: string,
    public attemptsUsed: number,
    public retryAfterSeconds: number
  ) {
    super(message);
    this.name = 'LockoutError';
  }
}

const API_URL = import.meta.env.VITE_API_URL || '';

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

interface TopicProgressSchema {
  steps_completed: number;
  steps_total: number;
  questions_passed: number;
  questions_total: number;
  percentage: number;
  status: 'not_started' | 'in_progress' | 'completed';
}

export interface TopicSummarySchema {
  id: string;
  slug: string;
  name: string;
  description: string;
  order: number;
  estimated_time: string;
  is_capstone: boolean;
  steps_count: number;
  questions_count: number;
  progress: TopicProgressSchema | null;
  is_locked: boolean;
}

interface SecondaryLinkSchema {
  text: string;
  url: string;
}

export interface ProviderOptionSchema {
  provider: string;
  title: string;
  url: string;
  description: string | null;
}

interface LearningStepSchema {
  order: number;
  text: string;
  action: string | null;
  title: string | null;
  url: string | null;
  description: string | null;
  code: string | null;
  secondary_links: SecondaryLinkSchema[];
  options: ProviderOptionSchema[];
}

export interface QuestionSchema {
  id: string;
  prompt: string;
  // Note: expected_concepts removed for security - grading data is server-side only
}

interface LearningObjectiveSchema {
  id: string;
  text: string;
  order: number;
}

export interface QuestionLockoutSchema {
  question_id: string;
  lockout_until: string;
  attempts_used: number;
}

export interface TopicDetailSchema {
  id: string;
  slug: string;
  name: string;
  description: string;
  order: number;
  estimated_time: string;
  is_capstone: boolean;
  learning_steps: LearningStepSchema[];
  questions: QuestionSchema[];
  learning_objectives: LearningObjectiveSchema[];
  progress: TopicProgressSchema | null;
  completed_step_orders: number[];
  passed_question_ids: string[];
  locked_questions: QuestionLockoutSchema[];
  is_locked: boolean;
  is_topic_locked: boolean;
  previous_topic_name: string | null;
}

export interface PhaseProgressSchema {
  steps_completed: number;
  steps_required: number;
  questions_passed: number;
  questions_required: number;
  hands_on_validated: number;
  hands_on_required: number;
  percentage: number;
  status: 'not_started' | 'in_progress' | 'completed';
}

export interface PhaseCapstoneOverviewSchema {
  title: string;
  summary: string;
  includes: string[];
  topic_slug: string | null;
}

export interface PhaseHandsOnVerificationOverviewSchema {
  summary: string;
  includes: string[];
}

export interface PhaseSummarySchema {
  id: number;
  name: string;
  slug: string;
  description: string;
  short_description: string;
  estimated_weeks: string;
  order: number;
  topics_count: number;
  objectives: string[];
  capstone: PhaseCapstoneOverviewSchema | null;
  hands_on_verification: PhaseHandsOnVerificationOverviewSchema | null;
  progress: PhaseProgressSchema | null;
  is_locked: boolean;
}

export interface HandsOnRequirement {
  id: string;
  phase_id: number;
  submission_type: string;
  name: string;
  description: string;
  example_url: string | null;
}

export interface HandsOnSubmission {
  id: number;
  requirement_id: string;
  submission_type: string;
  phase_id: number;
  submitted_value: string;
  extracted_username: string | null;
  is_validated: boolean;
  validated_at: string | null;
  created_at: string;
}

interface PhaseDetailSchema {
  id: number;
  name: string;
  slug: string;
  description: string;
  short_description: string;
  estimated_weeks: string;
  order: number;
  objectives: string[];
  capstone: PhaseCapstoneOverviewSchema | null;
  hands_on_verification: PhaseHandsOnVerificationOverviewSchema | null;
  topics: TopicSummarySchema[];
  progress: PhaseProgressSchema | null;
  hands_on_requirements: HandsOnRequirement[];
  hands_on_submissions: HandsOnSubmission[];
  is_locked: boolean;
  // Computed fields from API - DO NOT recalculate in frontend
  all_topics_complete: boolean;
  all_hands_on_validated: boolean;
  is_phase_complete: boolean;
}

interface UserSummarySchema {
  id: string;
  email: string;
  first_name: string | null;
  last_name: string | null;
  avatar_url: string | null;
  github_username: string | null;
  is_admin: boolean;
}

interface DashboardResponseNew {
  user: UserSummarySchema;
  phases: PhaseSummarySchema[];
  overall_progress: number;
  phases_completed: number;
  phases_total: number;
  current_phase: number | null;
  badges: BadgeSchema[];
}

interface BadgeSchema {
  id: string;
  name: string;
  description: string;
  icon: string;
}

/**
 * Create an API client with the given auth token getter.
 */
export function createApiClient(getToken: () => Promise<string | null>) {
  async function fetchWithAuth(url: string, options: RequestInit = {}) {
    const token = await getToken();

    const response = await fetch(`${API_URL}${url}`, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...options.headers,
      },
    });

    return response;
  }

  return {
    async getUserInfo(): Promise<UserInfo> {
      const res = await fetchWithAuth('/api/user/me');
      if (!res.ok) throw new Error('Failed to fetch user info');
      return res.json();
    },

    async getDashboard(): Promise<DashboardResponseNew> {
      const res = await fetchWithAuth('/api/user/dashboard');
      if (!res.ok) throw new Error('Failed to fetch dashboard');
      return res.json();
    },

    async getPhasesWithProgress(): Promise<PhaseSummarySchema[]> {
      const res = await fetchWithAuth('/api/user/phases');
      if (!res.ok) throw new Error('Failed to fetch phases');
      return res.json();
    },

    async getPhaseDetail(phaseSlug: string): Promise<PhaseDetailSchema | null> {
      const res = await fetchWithAuth(`/api/user/phases/${phaseSlug}`);
      if (res.status === 404) return null;
      if (!res.ok) throw new Error('Failed to fetch phase');
      return res.json();
    },

    async getTopicDetail(
      phaseSlug: string,
      topicSlug: string
    ): Promise<TopicDetailSchema | null> {
      const res = await fetchWithAuth(`/api/user/phases/${phaseSlug}/topics/${topicSlug}`);
      if (res.status === 404) return null;
      if (!res.ok) throw new Error('Failed to fetch topic');
      return res.json();
    },

    async submitGitHubUrl(
      requirementId: string,
      url: string
    ): Promise<GitHubValidationResult> {
      const res = await fetchWithAuth('/api/github/submit', {
        method: 'POST',
        body: JSON.stringify({ requirement_id: requirementId, submitted_value: url }),
      });
      if (!res.ok) {
        const error = await res.json().catch(() => ({ detail: 'Submission failed' }));
        throw new Error(error.detail || 'Submission failed');
      }
      return res.json();
    },

    async submitAnswer(
      topicId: string,
      questionId: string,
      answer: string
    ): Promise<QuestionSubmitResponse> {
      const res = await fetchWithAuth('/api/questions/submit', {
        method: 'POST',
        body: JSON.stringify({
          topic_id: topicId,
          question_id: questionId,
          user_answer: answer,
        }),
      });
      if (res.status === 429) {
        const error = await res.json().catch(() => ({
          detail: 'Too many attempts',
          lockout_until: null,
          attempts_used: 0,
        }));
        const retryAfter = parseInt(res.headers.get('Retry-After') || '3600', 10);
        throw new LockoutError(
          error.detail || 'Too many failed attempts',
          error.lockout_until,
          error.attempts_used,
          retryAfter
        );
      }
      if (!res.ok) {
        const error = await res.json().catch(() => ({ detail: 'Submission failed' }));
        throw new Error(error.detail || 'Submission failed');
      }
      return res.json();
    },

    async getTopicStepProgress(topicId: string): Promise<TopicStepProgress> {
      const res = await fetchWithAuth(`/api/steps/${topicId}`);
      if (!res.ok) {
        const error = await res.json().catch(() => ({ detail: 'Failed to fetch step progress' }));
        throw new Error(error.detail || 'Failed to fetch step progress');
      }
      return res.json();
    },

    async completeStep(
      topicId: string,
      stepOrder: number
    ): Promise<TopicStepProgress> {
      const res = await fetchWithAuth('/api/steps/complete', {
        method: 'POST',
        body: JSON.stringify({ topic_id: topicId, step_order: stepOrder }),
      });
      if (!res.ok) {
        const error = await res.json().catch(() => ({ detail: 'Failed to complete step' }));
        throw new Error(error.detail || 'Failed to complete step');
      }
      // The API returns StepProgressResponse, but we need to fetch full topic progress after
      return this.getTopicStepProgress(topicId);
    },

    async uncompleteStep(
      topicId: string,
      stepOrder: number
    ): Promise<TopicStepProgress> {
      const res = await fetchWithAuth(`/api/steps/${topicId}/${stepOrder}`, {
        method: 'DELETE',
      });
      if (!res.ok) {
        const error = await res.json().catch(() => ({ detail: 'Failed to uncomplete step' }));
        throw new Error(error.detail || 'Failed to uncomplete step');
      }
      // Refetch the full progress
      return this.getTopicStepProgress(topicId);
    },

    async getStreak(): Promise<StreakResponse> {
      const res = await fetchWithAuth('/api/activity/streak');
      if (!res.ok) {
        return {
          current_streak: 0,
          longest_streak: 0,
          total_activity_days: 0,
          last_activity_date: null,
          streak_alive: false,
        };
      }
      return res.json();
    },

    async getPublicProfile(username: string): Promise<PublicProfileResponse | null> {
      const res = await fetch(`${API_URL}/api/user/profile/${username}`);
      if (res.status === 404) return null;
      if (!res.ok) throw new Error('Failed to fetch profile');
      return res.json();
    },

    async getCertificateEligibility(certificateType: string): Promise<CertificateEligibility> {
      const res = await fetchWithAuth(`/api/certificates/eligibility/${certificateType}`);
      if (!res.ok) throw new Error('Failed to check eligibility');
      return res.json();
    },

    async generateCertificate(certificateType: string, recipientName: string): Promise<Certificate> {
      const res = await fetchWithAuth('/api/certificates', {
        method: 'POST',
        body: JSON.stringify({ certificate_type: certificateType, recipient_name: recipientName }),
      });
      if (!res.ok) {
        const error = await res.json().catch(() => ({ detail: 'Failed to generate' }));
        throw new Error(error.detail || 'Failed to generate certificate');
      }
      return res.json();
    },

    async getUserCertificates(): Promise<UserCertificates> {
      const res = await fetchWithAuth('/api/certificates');
      if (!res.ok) throw new Error('Failed to fetch certificates');
      return res.json();
    },

    async verifyCertificate(code: string): Promise<CertificateVerifyResponse> {
      const res = await fetch(`${API_URL}/api/certificates/verify/${code}`);
      if (!res.ok) {
        return {
          is_valid: false,
          certificate: null,
          message: 'Certificate not found',
        };
      }
      return res.json();
    },

    getCertificatePdfUrl(certificateId: number): string {
      return `${API_URL}/api/certificates/${certificateId}/pdf`;
    },

    getCertificatePngUrl(certificateId: number, scale?: number): string {
      const suffix = scale ? `?scale=${scale}` : '';
      return `${API_URL}/api/certificates/${certificateId}/png${suffix}`;
    },

    getVerifiedCertificatePdfUrl(code: string): string {
      return `${API_URL}/api/certificates/verify/${code}/pdf`;
    },

    getVerifiedCertificatePngUrl(code: string, scale?: number): string {
      const suffix = scale ? `?scale=${scale}` : '';
      return `${API_URL}/api/certificates/verify/${code}/png${suffix}`;
    },

    async getUpdates() {
      const res = await fetch(`${API_URL}/api/updates`);
      if (!res.ok) throw new Error('Failed to fetch updates');
      return res.json();
    },
  };
}
