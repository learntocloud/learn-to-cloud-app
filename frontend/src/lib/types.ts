/**
 * API types matching backend schemas.
 * Only includes types actually used by the frontend.
 */

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

export interface TaskResult {
  task_name: string;
  passed: boolean;
  feedback: string;
}

export interface GitHubValidationResult {
  is_valid: boolean;
  message: string;
  username_match: boolean;
  repo_exists: boolean;
  submission: Submission | null;
  task_results?: TaskResult[] | null;
  next_retry_at?: string | null;
}

export interface TopicStepProgress {
  topic_id: string;
  completed_steps: number[];  // List of step_order numbers that are complete
  total_steps: number;
  next_unlocked_step: number;  // The next step that can be completed (1-indexed)
}

export interface QuestionSubmitResponse {
  question_id: string;
  is_passed: boolean;
  llm_feedback: string | null;
  confidence_score: number | null;
  attempt_id: number;
  attempts_used: number | null;  // Failed attempts in lockout window (null if passed or re-practicing)
  lockout_until: string | null;  // ISO timestamp when lockout expires (set when max attempts reached)
}

export interface ScenarioQuestionResponse {
  question_id: string;
  scenario_prompt: string;
  base_prompt: string;
}

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

interface ActivityHeatmapResponse {
  days: ActivityHeatmapDay[];
  start_date: string;
  end_date: string;
  total_activities: number;
}

export interface PublicSubmission {
  requirement_id: string;
  submission_type: SubmissionType;
  phase_id: number;
  submitted_value: string;
  name: string;
  validated_at: string | null;
}

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

// Updates types (this week's commits)
export interface UpdatesCommit {
  sha: string;
  message: string;
  author: string;
  date: string;
  url: string;
  emoji: string;
  category: string;
}

export interface UpdatesRepo {
  owner: string;
  name: string;
}

export interface UpdatesResponse {
  week_start: string;
  week_display: string;
  commits: UpdatesCommit[];
  repo: UpdatesRepo;
  generated_at: string;
  error?: string;
}

// Admin Trends types
export interface DailyMetricsData {
  date: string;
  active_users: number;
  new_signups: number;
  returning_users: number;
  steps_completed: number;
  questions_attempted: number;
  questions_passed: number;
  hands_on_submitted: number;
  hands_on_validated: number;
  phases_completed: number;
  certificates_earned: number;
  question_pass_rate: number;
}

export interface TrendSummary {
  period_days: number;
  total_active_users: number;
  avg_daily_active_users: number;
  total_new_signups: number;
  total_steps_completed: number;
  total_questions_attempted: number;
  total_questions_passed: number;
  overall_pass_rate: number;
  total_phases_completed: number;
  total_certificates_earned: number;
  active_users_wow_change: number;
  cumulative_users: number;
  cumulative_certificates: number;
}

export interface TrendsResponse {
  days: DailyMetricsData[];
  summary: TrendSummary;
  start_date: string;
  end_date: string;
}
