/**
 * Hand-written API types that mirror the Python Pydantic schemas.
 *
 * When you change a schema in api/schemas.py, update the matching type here.
 * No codegen step required.
 */

// ---------------------------------------------------------------------------
// Enums
// ---------------------------------------------------------------------------

export type SubmissionType =
  | 'github_profile'
  | 'profile_readme'
  | 'repo_fork'
  | 'ctf_token'
  | 'networking_token'
  | 'journal_api_response'
  | 'code_analysis'
  | 'deployed_api'
  | 'container_image'
  | 'cicd_pipeline'
  | 'terraform_iac'
  | 'kubernetes_manifests'
  | 'security_scanning';

// ---------------------------------------------------------------------------
// Shared / Reusable
// ---------------------------------------------------------------------------

export interface Badge {
  id: string;
  name: string;
  description: string;
  icon: string;
}

export interface BadgeCatalogItem {
  id: string;
  name: string;
  description: string;
  icon: string;
  num: string;
  how_to: string;
  phase_id?: number | null;
  phase_name?: string | null;
}

export interface PhaseThemeData {
  phase_id: number;
  icon: string;
  bg_class: string;
  border_class: string;
  text_class: string;
}

export interface TaskResult {
  task_name: string;
  passed: boolean;
  feedback: string;
}

export interface ProviderOption {
  provider: string;
  title: string;
  url: string;
  description?: string | null;
}

export interface SecondaryLink {
  text: string;
  url: string;
}

export interface LearningObjective {
  id: string;
  text: string;
  order: number;
}

export interface LearningStep {
  order: number;
  text: string;
  action?: string | null;
  title?: string | null;
  url?: string | null;
  description?: string | null;
  code?: string | null;
  secondary_links?: SecondaryLink[];
  options?: ProviderOption[];
}

// ---------------------------------------------------------------------------
// Hands-On Requirements & Submissions
// ---------------------------------------------------------------------------

export interface HandsOnRequirement {
  id: string;
  phase_id: number;
  submission_type: SubmissionType;
  name: string;
  description: string;
  example_url?: string | null;
  note?: string | null;
  required_repo?: string | null;
}

export interface HandsOnSubmission {
  id: number;
  requirement_id: string;
  submission_type: SubmissionType;
  phase_id: number;
  submitted_value: string;
  extracted_username?: string | null;
  is_validated: boolean;
  validated_at?: string | null;
  created_at: string;
  feedback_json?: string | null;
}

export interface HandsOnValidationResult {
  is_valid: boolean;
  message: string;
  username_match?: boolean | null;
  repo_exists?: boolean | null;
  submission?: HandsOnSubmission | null;
  task_results?: TaskResult[] | null;
  next_retry_at?: string | null;
}

/** @deprecated Alias kept for existing imports */
export type GitHubValidationResult = HandsOnValidationResult;

// ---------------------------------------------------------------------------
// Public Profile
// ---------------------------------------------------------------------------

export interface PublicSubmission {
  requirement_id: string;
  submission_type: SubmissionType;
  phase_id: number;
  submitted_value: string;
  name: string;
  description?: string | null;
  validated_at?: string | null;
}

export interface PublicProfileResponse {
  username?: string | null;
  first_name?: string | null;
  avatar_url?: string | null;
  current_phase: number;
  phases_completed: number;
  member_since: string;
  submissions?: PublicSubmission[];
  badges?: Badge[];
}

// ---------------------------------------------------------------------------
// Progress
// ---------------------------------------------------------------------------

export interface PhaseProgressData {
  steps_completed: number;
  steps_required: number;
  hands_on_validated: number;
  hands_on_required: number;
  percentage: number;
  status: string;
}

export interface TopicProgressData {
  steps_completed: number;
  steps_total: number;
  percentage: number;
  status: string;
}

export interface StepProgressData {
  topic_id: string;
  completed_steps: number[];
  total_steps: number;
  next_unlocked_step: number;
}

// ---------------------------------------------------------------------------
// Phase & Topic detail
// ---------------------------------------------------------------------------

export interface PhaseCapstoneOverview {
  title: string;
  summary: string;
  includes?: string[];
  topic_slug?: string | null;
}

export interface PhaseHandsOnVerificationOverview {
  summary: string;
  includes?: string[];
  requirements?: HandsOnRequirement[];
}

export interface TopicSummaryData {
  id: string;
  name: string;
  slug: string;
  description: string;
  order: number;
  is_capstone: boolean;
  is_locked: boolean;
  steps_count: number;
  progress?: TopicProgressData | null;
}

export interface TopicDetailData {
  id: string;
  name: string;
  slug: string;
  description: string;
  order: number;
  is_capstone: boolean;
  is_locked: boolean;
  is_topic_locked: boolean;
  learning_objectives?: LearningObjective[];
  learning_steps: LearningStep[];
  completed_step_orders?: number[];
  previous_topic_name?: string | null;
  progress?: TopicProgressData | null;
}

export interface PhaseSummaryData {
  id: number;
  name: string;
  slug: string;
  description: string;
  short_description: string;
  order: number;
  topics_count: number;
  objectives?: string[];
  capstone?: PhaseCapstoneOverview | null;
  hands_on_verification?: PhaseHandsOnVerificationOverview | null;
  progress?: PhaseProgressData | null;
  is_locked: boolean;
}

export interface PhaseDetailData {
  id: number;
  name: string;
  slug: string;
  description: string;
  short_description: string;
  order: number;
  objectives: string[];
  capstone?: PhaseCapstoneOverview | null;
  hands_on_verification?: PhaseHandsOnVerificationOverview | null;
  topics: TopicSummaryData[];
  progress?: PhaseProgressData | null;
  hands_on_requirements?: HandsOnRequirement[];
  hands_on_submissions?: HandsOnSubmission[];
  is_locked: boolean;
  all_topics_complete: boolean;
  all_hands_on_validated: boolean;
  is_phase_complete: boolean;
}

// ---------------------------------------------------------------------------
// User
// ---------------------------------------------------------------------------

export interface UserResponse {
  id: string;
  email: string;
  first_name?: string | null;
  last_name?: string | null;
  avatar_url?: string | null;
  github_username?: string | null;
  is_admin: boolean;
  created_at: string;
}

export interface UserSummaryData {
  id: string;
  email: string;
  first_name?: string | null;
  last_name?: string | null;
  avatar_url?: string | null;
  github_username?: string | null;
  is_admin: boolean;
}

// ---------------------------------------------------------------------------
// Dashboard
// ---------------------------------------------------------------------------

export interface DashboardData {
  user: UserSummaryData;
  phases: PhaseSummaryData[];
  overall_progress: number;
  phases_completed: number;
  phases_total: number;
  current_phase?: number | null;
  badges?: Badge[];
}

// ---------------------------------------------------------------------------
// Certificates
// ---------------------------------------------------------------------------

export interface CertificateData {
  id: number;
  certificate_type: string;
  verification_code: string;
  recipient_name: string;
  issued_at: string;
  phases_completed: number;
  total_phases: number;
}

export interface CertificateEligibilityResponse {
  is_eligible: boolean;
  certificate_type: string;
  phases_completed: number;
  total_phases: number;
  completion_percentage: number;
  already_issued: boolean;
  existing_certificate_id?: number | null;
  message: string;
}

export interface CertificateVerifyResponse {
  is_valid: boolean;
  certificate?: CertificateData | null;
  message: string;
}

export interface UserCertificatesResponse {
  certificates: CertificateData[];
  full_completion_eligible: boolean;
}

// ---------------------------------------------------------------------------
// Badge Catalog
// ---------------------------------------------------------------------------

export interface BadgeCatalogResponse {
  phase_badges: BadgeCatalogItem[];
  total_badges: number;
  phase_themes: PhaseThemeData[];
}

// ---------------------------------------------------------------------------
// Activity Heatmap
// ---------------------------------------------------------------------------

export interface ActivityHeatmapDay {
  date: string;
  count: number;
}

export interface ActivityHeatmapResponse {
  days: ActivityHeatmapDay[];
}
