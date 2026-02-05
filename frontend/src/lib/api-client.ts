/**
 * API client for Learn to Cloud backend.
 * Uses Clerk for authentication.
 *
 * Types are generated from api/openapi.json via openapi-typescript.
 * Run `npm run generate:api` after changing Python schemas.
 */

import type {
  ActivityHeatmapResponse,
  BadgeCatalogResponse,
  CertificateData,
  CertificateEligibilityResponse,
  CertificateVerifyResponse,
  DashboardData,
  HandsOnValidationResult,
  PhaseDetailData,
  PhaseSummaryData,
  PublicProfileResponse,
  StepProgressData,
  TopicDetailData,
  UserCertificatesResponse,
  UserResponse,
} from './types';

// Re-export types that consumers import from this module
export type {
  HandsOnRequirement,
  HandsOnSubmission,
  ProviderOption as ProviderOptionSchema,
  TopicDetailData as TopicDetailSchema,
  TopicSummaryData as TopicSummarySchema,
  PhaseSummaryData as PhaseSummarySchema,
  PhaseProgressData as PhaseProgressSchema,
} from './types';

const API_URL = import.meta.env.VITE_API_URL || '';

// ---------------------------------------------------------------------------
// Fetch helpers
// ---------------------------------------------------------------------------

type ErrorDetail = {
  detail?: string;
  lockout_until?: string | null;
  attempts_used?: number | null;
};

class ApiError extends Error {
  status: number;
  detail: ErrorDetail;

  constructor(status: number, detail: ErrorDetail) {
    super(detail.detail ?? `API error ${status}`);
    this.status = status;
    this.detail = detail;
  }
}

async function request<T>(
  url: string,
  init: RequestInit,
  fallback: string,
): Promise<{ data: T; response: Response }> {
  const response = await fetch(`${API_URL}${url}`, init);

  if (!response.ok) {
    let detail: ErrorDetail = {};
    try {
      detail = (await response.json()) as ErrorDetail;
    } catch {
      /* no parseable body */
    }
    throw new ApiError(response.status, {
      detail: detail.detail ?? fallback,
      lockout_until: detail.lockout_until,
      attempts_used: detail.attempts_used,
    });
  }

  const data = (await response.json()) as T;
  return { data, response };
}

// ---------------------------------------------------------------------------
// Client factory
// ---------------------------------------------------------------------------

/**
 * Create an API client with the given auth token getter.
 */
export function createApiClient(getToken: () => Promise<string | null>) {
  async function authHeaders(): Promise<HeadersInit> {
    const token = await getToken();
    return {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    };
  }

  async function get<T>(url: string, fallback: string): Promise<T> {
    const { data } = await request<T>(url, { headers: await authHeaders() }, fallback);
    return data;
  }

  async function getPublic<T>(url: string, fallback: string): Promise<T> {
    const { data } = await request<T>(url, {}, fallback);
    return data;
  }

  async function post<T>(url: string, body: unknown, fallback: string): Promise<T> {
    const { data } = await request<T>(
      url,
      { method: 'POST', headers: await authHeaders(), body: JSON.stringify(body) },
      fallback,
    );
    return data;
  }

  async function del(url: string, fallback: string): Promise<void> {
    await request<unknown>(url, { method: 'DELETE', headers: await authHeaders() }, fallback);
  }

  return {
    // ---- User ----
    getUserInfo: () => get<UserResponse>('/api/user/me', 'Failed to fetch user info'),

    // ---- Dashboard ----
    getDashboard: () => get<DashboardData>('/api/user/dashboard', 'Failed to fetch dashboard'),

    // ---- Phases ----
    getPhasesWithProgress: () =>
      get<PhaseSummaryData[]>('/api/user/phases', 'Failed to fetch phases'),

    async getPhaseDetail(phaseSlug: string): Promise<PhaseDetailData | null> {
      try {
        return await get<PhaseDetailData>(
          `/api/user/phases/${encodeURIComponent(phaseSlug)}`,
          'Failed to fetch phase',
        );
      } catch (e) {
        if (e instanceof ApiError && e.status === 404) return null;
        throw e;
      }
    },

    // ---- Topics ----
    async getTopicDetail(
      phaseSlug: string,
      topicSlug: string,
    ): Promise<TopicDetailData | null> {
      try {
        return await get<TopicDetailData>(
          `/api/user/phases/${encodeURIComponent(phaseSlug)}/topics/${encodeURIComponent(topicSlug)}`,
          'Failed to fetch topic',
        );
      } catch (e) {
        if (e instanceof ApiError && e.status === 404) return null;
        throw e;
      }
    },

    // ---- Badges ----
    getBadgeCatalog: () =>
      get<BadgeCatalogResponse>('/api/user/badges/catalog', 'Failed to fetch badge catalog'),

    // ---- Hands-on submissions ----
    submitGitHubUrl: (requirementId: string, url: string) =>
      post<HandsOnValidationResult>('/api/github/submit', {
        requirement_id: requirementId,
        submitted_value: url,
      }, 'Submission failed'),

    // ---- Steps ----
    getTopicStepProgress: (topicId: string) =>
      get<StepProgressData>(
        `/api/steps/${encodeURIComponent(topicId)}`,
        'Failed to fetch step progress',
      ),

    async completeStep(topicId: string, stepOrder: number): Promise<StepProgressData> {
      await post<unknown>('/api/steps/complete', {
        topic_id: topicId,
        step_order: stepOrder,
      }, 'Failed to complete step');
      return this.getTopicStepProgress(topicId);
    },

    async uncompleteStep(topicId: string, stepOrder: number): Promise<StepProgressData> {
      await del(
        `/api/steps/${encodeURIComponent(topicId)}/${stepOrder}`,
        'Failed to uncomplete step',
      );
      return this.getTopicStepProgress(topicId);
    },

    // ---- Public profile ----
    async getPublicProfile(username: string): Promise<PublicProfileResponse | null> {
      try {
        return await getPublic<PublicProfileResponse>(
          `/api/user/profile/${encodeURIComponent(username)}`,
          'Failed to fetch profile',
        );
      } catch (e) {
        if (e instanceof ApiError && e.status === 404) return null;
        throw e;
      }
    },

    async getActivityHeatmap(username: string): Promise<ActivityHeatmapResponse | null> {
      try {
        return await getPublic<ActivityHeatmapResponse>(
          `/api/user/profile/${encodeURIComponent(username)}/heatmap`,
          'Failed to fetch activity heatmap',
        );
      } catch (e) {
        if (e instanceof ApiError && e.status === 404) return null;
        throw e;
      }
    },

    // ---- Certificates ----
    getCertificateEligibility: (certificateType: string) =>
      get<CertificateEligibilityResponse>(
        `/api/certificates/eligibility/${encodeURIComponent(certificateType)}`,
        'Failed to check eligibility',
      ),

    generateCertificate: (certificateType: string, recipientName: string) =>
      post<CertificateData>('/api/certificates', {
        certificate_type: certificateType,
        recipient_name: recipientName,
      }, 'Failed to generate certificate'),

    getUserCertificates: () =>
      get<UserCertificatesResponse>('/api/certificates', 'Failed to fetch certificates'),

    async verifyCertificate(code: string): Promise<CertificateVerifyResponse> {
      try {
        return await getPublic<CertificateVerifyResponse>(
          `/api/certificates/verify/${encodeURIComponent(code)}`,
          'Certificate not found',
        );
      } catch {
        return { is_valid: false, certificate: null, message: 'Certificate not found' };
      }
    },

    // ---- Certificate asset URLs ----
    getCertificatePdfUrl: (certificateId: number) =>
      `${API_URL}/api/certificates/${certificateId}/pdf`,

    getCertificatePngUrl: (certificateId: number, scale?: number) =>
      `${API_URL}/api/certificates/${certificateId}/png${scale ? `?scale=${scale}` : ''}`,

    getVerifiedCertificatePdfUrl: (code: string) =>
      `${API_URL}/api/certificates/verify/${code}/pdf`,

    getVerifiedCertificatePngUrl: (code: string, scale?: number) =>
      `${API_URL}/api/certificates/verify/${code}/png${scale ? `?scale=${scale}` : ''}`,
  };
}
