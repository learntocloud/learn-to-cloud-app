/**
 * Shared constants used across the frontend.
 */

/** Certificate types */
export const CERTIFICATE_TYPES = {
  FULL_COMPLETION: 'full_completion',
} as const;

export type CertificateType = (typeof CERTIFICATE_TYPES)[keyof typeof CERTIFICATE_TYPES];

/** Progress status values from the API */
export const PROGRESS_STATUS = {
  NOT_STARTED: 'not_started',
  IN_PROGRESS: 'in_progress',
  COMPLETED: 'completed',
} as const;

export type ProgressStatus = (typeof PROGRESS_STATUS)[keyof typeof PROGRESS_STATUS];

/** Valid phase slugs */
export const VALID_PHASE_SLUGS = [
  'phase0',
  'phase1',
  'phase2',
  'phase3',
  'phase4',
  'phase5',
  'phase6',
] as const;

export type PhaseSlug = (typeof VALID_PHASE_SLUGS)[number];

/** Type guard to check if a string is a valid phase slug */
export function isValidPhaseSlug(slug: string): slug is PhaseSlug {
  return (VALID_PHASE_SLUGS as readonly string[]).includes(slug);
}

/** API base URL */
export const API_URL = import.meta.env.VITE_API_URL || '';
