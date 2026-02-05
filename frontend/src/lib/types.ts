/**
 * API types re-exported from generated OpenAPI types.
 *
 * Generated types are in api-types.generated.ts (auto-generated from api/openapi.json).
 * Run `npm run generate:api` after changing Python schemas.
 *
 * Frontend-only types that aren't in the OpenAPI spec are defined at the bottom.
 */

import type { components } from './api-types.generated';

// ---------------------------------------------------------------------------
// Re-export generated types with clean names
// ---------------------------------------------------------------------------

// Enums
export type SubmissionType = components['schemas']['SubmissionType'];

// Shared / Reusable
export type Badge = components['schemas']['BadgeData'];
export type BadgeCatalogItem = components['schemas']['BadgeCatalogItem'];
export type PhaseThemeData = components['schemas']['PhaseThemeData'];
export type TaskResult = components['schemas']['TaskResult'];
export type ProviderOption = components['schemas']['ProviderOption'];
export type SecondaryLink = components['schemas']['SecondaryLink'];
export type LearningObjective = components['schemas']['LearningObjective'];
export type LearningStep = components['schemas']['LearningStep'];

// Hands-On Requirements & Submissions
export type HandsOnRequirement = components['schemas']['HandsOnRequirement'];
export type HandsOnSubmission = components['schemas']['HandsOnSubmissionResponse'];
export type HandsOnValidationResult = components['schemas']['HandsOnValidationResult'];

// Public Profile
export type PublicSubmission = components['schemas']['PublicSubmission'];
export type PublicProfileResponse = components['schemas']['PublicProfileResponse'];

// Progress
export type PhaseProgressData = components['schemas']['PhaseProgressData'];
export type TopicProgressData = components['schemas']['TopicProgressData'];
export type StepProgressData = components['schemas']['StepProgressData'];

// Phase & Topic detail
export type PhaseCapstoneOverview = components['schemas']['PhaseCapstoneOverview'];
export type PhaseHandsOnVerificationOverview = components['schemas']['PhaseHandsOnVerificationOverview'];
export type TopicSummaryData = components['schemas']['TopicSummaryData'];
export type TopicDetailData = components['schemas']['TopicDetailData'];
export type PhaseSummaryData = components['schemas']['PhaseSummaryData'];
export type PhaseDetailData = components['schemas']['PhaseDetailData'];

// User
export type UserResponse = components['schemas']['UserResponse'];
export type UserSummaryData = components['schemas']['UserSummaryData'];

// Dashboard
export type DashboardData = components['schemas']['DashboardData'];

// Certificates
export type CertificateData = components['schemas']['CertificateData'];
export type CertificateEligibilityResponse = components['schemas']['CertificateEligibilityResponse'];
export type CertificateVerifyResponse = components['schemas']['CertificateVerifyResponse'];
export type UserCertificatesResponse = components['schemas']['UserCertificatesResponse'];

// Badge Catalog
export type BadgeCatalogResponse = components['schemas']['BadgeCatalogResponse'];

// ---------------------------------------------------------------------------
// Frontend-only types (not in OpenAPI spec)
// ---------------------------------------------------------------------------

export interface ActivityHeatmapDay {
  date: string;
  count: number;
}

export interface ActivityHeatmapResponse {
  days: ActivityHeatmapDay[];
}
