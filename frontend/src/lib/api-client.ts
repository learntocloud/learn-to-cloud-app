/**
 * API client for Learn to Cloud backend.
 * Uses Clerk for authentication.
 *
 * This client is generated from the OpenAPI contract and wraps openapi-fetch.
 */

import createClient from 'openapi-fetch';
import type { components, paths } from './api/schema';
import type { GitHubValidationResult } from './types';

export type { GitHubValidationResult } from './types';
export type BadgeCatalogItem = components['schemas']['BadgeCatalogItem'];
export type BadgeCatalogResponse =
  paths['/api/user/badges/catalog']['get']['responses']['200']['content']['application/json'];
export type HandsOnRequirement = components['schemas']['HandsOnRequirement'];
export type HandsOnSubmission = components['schemas']['HandsOnSubmissionResponse'];
export type PhaseProgressSchema = components['schemas']['PhaseProgressData'];
export type PhaseSummarySchema = components['schemas']['PhaseSummaryData'];
export type ProviderOptionSchema = components['schemas']['ProviderOption'];
export type QuestionSchema = components['schemas']['Question'];
export type TopicDetailSchema = components['schemas']['TopicDetailData'];
export type TopicSummarySchema = components['schemas']['TopicSummaryData'];

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

type ErrorDetail = {
  detail?: string;
  lockout_until?: string | null;
  attempts_used?: number | null;
};

type UserInfo = paths['/api/user/me']['get']['responses']['200']['content']['application/json'];
type DashboardResponse =
  paths['/api/user/dashboard']['get']['responses']['200']['content']['application/json'];
type PhaseSummary =
  paths['/api/user/phases']['get']['responses']['200']['content']['application/json'][number];
type PhaseDetail =
  paths['/api/user/phases/{phase_slug}']['get']['responses']['200']['content']['application/json'];
type TopicDetail =
  paths['/api/user/phases/{phase_slug}/topics/{topic_slug}']['get']['responses']['200']['content']['application/json'];
type ScenarioQuestionResponse =
  paths['/api/questions/{topic_id}/{question_id}/scenario']['get']['responses']['200']['content']['application/json'];
type QuestionSubmitResponse =
  paths['/api/questions/submit']['post']['responses']['200']['content']['application/json'];
type TopicStepProgress =
  paths['/api/steps/{topic_id}']['get']['responses']['200']['content']['application/json'];
type StreakResponse =
  paths['/api/activity/streak']['get']['responses']['200']['content']['application/json'];
type PublicProfileResponse =
  paths['/api/user/profile/{username}']['get']['responses']['200']['content']['application/json'];
type CertificateEligibility =
  paths['/api/certificates/eligibility/{certificate_type}']['get']['responses']['200']['content']['application/json'];
type Certificate =
  paths['/api/certificates']['post']['responses']['201']['content']['application/json'];
type CertificateVerifyResponse =
  paths['/api/certificates/verify/{verification_code}']['get']['responses']['200']['content']['application/json'];
type UserCertificates =
  paths['/api/certificates']['get']['responses']['200']['content']['application/json'];
type UpdatesResponse =
  paths['/api/updates']['get']['responses']['200']['content']['application/json'];

function getErrorDetail(error: unknown): ErrorDetail {
  if (error && typeof error === 'object') {
    const detail = error as ErrorDetail;
    return detail;
  }
  return {};
}

function getErrorMessage(error: unknown, fallback: string): string {
  const detail = getErrorDetail(error).detail;
  return detail || fallback;
}

function ensureData<T>(
  data: T | undefined,
  error: unknown,
  response: Response | undefined,
  fallback: string
): T {
  if (response?.ok && data !== undefined) {
    return data;
  }
  throw new Error(getErrorMessage(error, fallback));
}

/**
 * Create an API client with the given auth token getter.
 */
export function createApiClient(getToken: () => Promise<string | null>) {
  const client = createClient<paths>({ baseUrl: API_URL });

  async function getAuthHeaders() {
    const token = await getToken();
    return {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    } as const;
  }

  return {
    async getUserInfo(): Promise<UserInfo> {
      const { data, error, response } = await client.GET('/api/user/me', {
        headers: await getAuthHeaders(),
      });
      return ensureData(data, error, response, 'Failed to fetch user info');
    },

    async getDashboard(): Promise<DashboardResponse> {
      const { data, error, response } = await client.GET('/api/user/dashboard', {
        headers: await getAuthHeaders(),
      });
      return ensureData(data, error, response, 'Failed to fetch dashboard');
    },

    async getPhasesWithProgress(): Promise<PhaseSummary[]> {
      const { data, error, response } = await client.GET('/api/user/phases', {
        headers: await getAuthHeaders(),
      });
      return ensureData(data, error, response, 'Failed to fetch phases');
    },

    async getPhaseDetail(phaseSlug: string): Promise<PhaseDetail | null> {
      const { data, error, response } = await client.GET('/api/user/phases/{phase_slug}', {
        headers: await getAuthHeaders(),
        params: { path: { phase_slug: phaseSlug } },
      });
      if (response?.status === 404) return null;
      return ensureData(data, error, response, 'Failed to fetch phase');
    },

    async getTopicDetail(
      phaseSlug: string,
      topicSlug: string
    ): Promise<TopicDetail | null> {
      const { data, error, response } = await client.GET(
        '/api/user/phases/{phase_slug}/topics/{topic_slug}',
        {
          headers: await getAuthHeaders(),
          params: { path: { phase_slug: phaseSlug, topic_slug: topicSlug } },
        }
      );
      if (response?.status === 404) return null;
      return ensureData(data, error, response, 'Failed to fetch topic');
    },

    async submitGitHubUrl(
      requirementId: string,
      url: string
    ): Promise<GitHubValidationResult> {
      const { data, error, response } = await client.POST('/api/github/submit', {
        headers: await getAuthHeaders(),
        body: { requirement_id: requirementId, submitted_value: url },
      });
      return ensureData(data, error, response, 'Submission failed');
    },

    async getScenarioQuestion(
      topicId: string,
      questionId: string
    ): Promise<ScenarioQuestionResponse> {
      const { data, error, response } = await client.GET(
        '/api/questions/{topic_id}/{question_id}/scenario',
        {
          headers: await getAuthHeaders(),
          params: { path: { topic_id: topicId, question_id: questionId } },
        }
      );
      if (response?.status === 429) {
        const detail = getErrorDetail(error);
        const retryAfter = parseInt(response.headers.get('Retry-After') || '3600', 10);
        throw new LockoutError(
          detail.detail || 'Too many failed attempts',
          detail.lockout_until || '',
          detail.attempts_used ?? 0,
          retryAfter
        );
      }
      return ensureData(data, error, response, 'Failed to fetch question');
    },

    async submitAnswer(
      topicId: string,
      questionId: string,
      answer: string,
      scenarioContext?: string
    ): Promise<QuestionSubmitResponse> {
      const { data, error, response } = await client.POST('/api/questions/submit', {
        headers: await getAuthHeaders(),
        body: {
          topic_id: topicId,
          question_id: questionId,
          user_answer: answer,
          scenario_context: scenarioContext,
        },
      });
      if (response?.status === 429) {
        const detail = getErrorDetail(error);
        const retryAfter = parseInt(response.headers.get('Retry-After') || '3600', 10);
        throw new LockoutError(
          detail.detail || 'Too many failed attempts',
          detail.lockout_until || '',
          detail.attempts_used ?? 0,
          retryAfter
        );
      }
      return ensureData(data, error, response, 'Submission failed');
    },

    async getTopicStepProgress(topicId: string): Promise<TopicStepProgress> {
      const { data, error, response } = await client.GET('/api/steps/{topic_id}', {
        headers: await getAuthHeaders(),
        params: { path: { topic_id: topicId } },
      });
      return ensureData(data, error, response, 'Failed to fetch step progress');
    },

    async completeStep(
      topicId: string,
      stepOrder: number
    ): Promise<TopicStepProgress> {
      const { error, response } = await client.POST('/api/steps/complete', {
        headers: await getAuthHeaders(),
        body: { topic_id: topicId, step_order: stepOrder },
      });
      if (!response?.ok) {
        throw new Error(getErrorMessage(error, 'Failed to complete step'));
      }
      return this.getTopicStepProgress(topicId);
    },

    async uncompleteStep(
      topicId: string,
      stepOrder: number
    ): Promise<TopicStepProgress> {
      const { error, response } = await client.DELETE('/api/steps/{topic_id}/{step_order}', {
        headers: await getAuthHeaders(),
        params: { path: { topic_id: topicId, step_order: stepOrder } },
      });
      if (!response?.ok) {
        throw new Error(getErrorMessage(error, 'Failed to uncomplete step'));
      }
      return this.getTopicStepProgress(topicId);
    },

    async getStreak(): Promise<StreakResponse> {
      const { data, response } = await client.GET('/api/activity/streak', {
        headers: await getAuthHeaders(),
      });
      if (!response?.ok || !data) {
        return {
          current_streak: 0,
          longest_streak: 0,
          total_activity_days: 0,
          last_activity_date: null,
          streak_alive: false,
        };
      }
      return data;
    },

    async getPublicProfile(username: string): Promise<PublicProfileResponse | null> {
      const { data, error, response } = await client.GET('/api/user/profile/{username}', {
        params: { path: { username } },
      });
      if (response?.status === 404) return null;
      return ensureData(data, error, response, 'Failed to fetch profile');
    },

    async getCertificateEligibility(certificateType: string): Promise<CertificateEligibility> {
      const { data, error, response } = await client.GET(
        '/api/certificates/eligibility/{certificate_type}',
        {
          headers: await getAuthHeaders(),
          params: { path: { certificate_type: certificateType } },
        }
      );
      return ensureData(data, error, response, 'Failed to check eligibility');
    },

    async generateCertificate(
      certificateType: string,
      recipientName: string
    ): Promise<Certificate> {
      const { data, error, response } = await client.POST('/api/certificates', {
        headers: await getAuthHeaders(),
        body: { certificate_type: certificateType, recipient_name: recipientName },
      });
      return ensureData(data, error, response, 'Failed to generate certificate');
    },

    async getUserCertificates(): Promise<UserCertificates> {
      const { data, error, response } = await client.GET('/api/certificates', {
        headers: await getAuthHeaders(),
      });
      return ensureData(data, error, response, 'Failed to fetch certificates');
    },

    async verifyCertificate(code: string): Promise<CertificateVerifyResponse> {
      const { data, response } = await client.GET(
        '/api/certificates/verify/{verification_code}',
        {
          params: { path: { verification_code: code } },
        }
      );
      if (!response?.ok || !data) {
        return {
          is_valid: false,
          certificate: null,
          message: 'Certificate not found',
        };
      }
      return data;
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

    async getUpdates(): Promise<UpdatesResponse> {
      const { data, error, response } = await client.GET('/api/updates');
      return ensureData(data, error, response, 'Failed to fetch updates');
    },

    async getBadgeCatalog(): Promise<BadgeCatalogResponse> {
      const { data, error, response } = await client.GET('/api/user/badges/catalog');
      return ensureData(data, error, response, 'Failed to fetch badge catalog');
    },
  };
}
