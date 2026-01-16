/**
 * API types matching backend schemas.
 * Only includes types actually used by the frontend.
 */

// ============ GitHub Submission Types ============

export type SubmissionType =
  | 'github_profile'   // GitHub profile URL
  | 'profile_readme'   // GitHub profile README
  | 'repo_fork'        // Fork of a required repository
  | 'repo_url'         // Any repository URL
  | 'deployed_app'     // Live deployed application
  | 'ctf_token'        // CTF challenge completion token
  | 'api_challenge'    // API-based challenge response
  | 'journal_api_response'  // Local API JSON response validation
  | 'workflow_run'     // GitHub Actions workflow run verification
  | 'repo_with_files'  // Repository with specific files (Dockerfile, *.tf, etc.)
  | 'container_image'; // Public container image (Docker Hub, GHCR)

export interface Submission {
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

export interface GitHubValidationResult {
  is_valid: boolean;
  message: string;
  username_match: boolean;
  repo_exists: boolean;
  submission: Submission | null;
}

// ============ Step Progress Types ============

export interface TopicStepProgress {
  topic_id: string;
  completed_steps: number[];  // List of step_order numbers that are complete
  total_steps: number;
  next_unlocked_step: number;  // The next step that can be completed (1-indexed)
}

// ============ Question Types ============

export interface QuestionSubmitResponse {
  question_id: string;
  is_passed: boolean;
  llm_feedback: string | null;
  confidence_score: number | null;
  attempt_id: number;
}

// ============ Streak & Activity Types ============

export interface StreakResponse {
  current_streak: number;
  longest_streak: number;
  total_activity_days: number;
  last_activity_date: string | null;
  streak_alive: boolean;
}

export interface ActivityHeatmapDay {
  date: string;
  count: number;
  activity_types: string[];
}

export interface ActivityHeatmapResponse {
  days: ActivityHeatmapDay[];
  start_date: string;
  end_date: string;
  total_activities: number;
}

// ============ Public Profile Types ============

export interface PublicSubmission {
  requirement_id: string;
  submission_type: SubmissionType;
  phase_id: number;
  submitted_value: string;
  name: string;
  validated_at: string | null;
}

// ============ Badge Types ============

export interface Badge {
  id: string;
  name: string;
  description: string;
  icon: string;
}

export interface PublicProfileResponse {
  username: string | null;
  first_name: string | null;
  avatar_url: string | null;
  current_phase: number;
  phases_completed: number;
  streak: StreakResponse;
  activity_heatmap: ActivityHeatmapResponse;
  member_since: string;
  submissions: PublicSubmission[];
  badges: Badge[];
}

// ============ Certificate Types ============

export interface CertificateEligibility {
  is_eligible: boolean;
  certificate_type: string;
  phases_completed: number;
  total_phases: number;
  completion_percentage: number;
  already_issued: boolean;
  existing_certificate_id: number | null;
  message: string;
}

export interface Certificate {
  id: number;
  certificate_type: string;
  verification_code: string;
  recipient_name: string;
  issued_at: string;
  phases_completed: number;
  total_phases: number;
}

export interface CertificateVerifyResponse {
  is_valid: boolean;
  certificate: Certificate | null;
  message: string;
}

export interface UserCertificates {
  certificates: Certificate[];
  full_completion_eligible: boolean;
}
