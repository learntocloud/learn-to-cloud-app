/* API types matching backend schemas */

export type CompletionStatus = 'not_started' | 'in_progress' | 'completed';

// Cloud provider option for steps with multiple provider paths
export interface ProviderOption {
  provider: 'aws' | 'azure' | 'gcp';
  title: string;
  url: string;
  description?: string;
}

export interface LearningStep {
  order: number;
  text: string;
  url: string | null;
  // Rich content fields (optional)
  action?: string;         // Bold action word: "Study", "Create", "Install", etc.
  title?: string;          // Link text separate from action
  description?: string;    // Additional context paragraph below
  code?: string;           // Code block content
  secondary_links?: { text: string; url: string }[];  // Additional links in the description
  options?: ProviderOption[];  // Cloud provider-specific options (renders as tabs)
}

// Learning objectives displayed at top of topic (not tracked)
export interface LearningObjective {
  id: string;
  text: string;
  order: number;
}

export interface Topic {
  id: string;
  name: string;
  slug: string;
  description: string;
  short_description?: string;
  order: number;
  estimated_time: string | null;
  learning_steps: LearningStep[];
  learning_objectives: LearningObjective[];
  questions?: KnowledgeQuestion[];
  is_capstone: boolean;
}

export interface TopicWithProgress {
  id: string;
  name: string;
  slug: string;
  description: string;
  order: number;
  estimated_time: string | null;
  learning_steps: LearningStep[];
  learning_objectives: LearningObjective[];
  questions?: KnowledgeQuestion[];
  is_capstone: boolean;
  questions_passed: number;
  questions_total: number;
  steps_completed: number;
  steps_total: number;
}

export interface PhaseProgress {
  phase_id: number;
  questions_passed: number;
  questions_total: number;
  percentage: number;
  status: CompletionStatus;
}

export interface Phase {
  id: number;
  name: string;
  slug: string;
  description: string;
  short_description: string;
  estimated_weeks: string;
  order: number;
  prerequisites: string[];
  objectives: string[];
  topics: Topic[];
}

export interface PhaseWithProgress extends Phase {
  progress: PhaseProgress | null;
  isLocked: boolean;
}

export interface PhaseDetailWithProgress {
  id: number;
  name: string;
  slug: string;
  description: string;
  estimated_weeks: string;
  order: number;
  prerequisites: string[];
  topics: TopicWithProgress[];
  progress: PhaseProgress | null;
}

export interface User {
  id: string;
  email: string;
  first_name: string | null;
  last_name: string | null;
  avatar_url: string | null;
  github_username: string | null;
  created_at: string;
}

export interface DashboardResponse {
  user: User;
  phases: PhaseWithProgress[];
  overall_progress: number;
  // Simplified progress - just phases
  phases_completed: number;
  phases_total: number;
  current_phase: number | null;
}

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

export interface GitHubRequirement {
  id: string;
  phase_id: number;
  submission_type: SubmissionType;
  name: string;
  description: string;
  example_url: string | null;
  required_repo: string | null;
  expected_endpoint: string | null;
  required_file_patterns: string[] | null;
  file_description: string | null;
}

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

export interface PhaseGitHubRequirements {
  phase_id: number;
  requirements: GitHubRequirement[];
  submissions: Submission[];
  has_requirements: boolean;  // False if phase has no requirements defined
  all_validated: boolean;
}

// ============ Step Progress Types ============

export interface StepProgress {
  topic_id: string;
  step_order: number;
  completed_at: string;
}

export interface TopicStepProgress {
  topic_id: string;
  completed_steps: number[];  // List of step_order numbers that are complete
  total_steps: number;
  next_unlocked_step: number;  // The next step that can be completed (1-indexed)
}

// ============ Knowledge Question Types ============

export interface KnowledgeQuestion {
  id: string;
  prompt: string;
  expected_concepts: string[];
}

export interface QuestionStatus {
  question_id: string;
  is_passed: boolean;
  attempts_count: number;
  last_attempt_at: string | null;
}

export interface TopicQuestionsStatus {
  topic_id: string;
  questions: QuestionStatus[];
  all_passed: boolean;
  total_questions: number;
  passed_questions: number;
}

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

export type ActivityType = 
  | 'question_attempt' 
  | 'step_complete'
  | 'topic_complete' 
  | 'hands_on_validated'
  | 'phase_complete'
  | 'certificate_earned';

export interface ActivityHeatmapDay {
  date: string;
  count: number;
  activity_types: ActivityType[];
}

export interface ActivityHeatmapResponse {
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
  phases_completed: number;  // Count of fully completed phases (steps + questions + GitHub)
  streak: StreakResponse;
  activity_heatmap: ActivityHeatmapResponse;
  member_since: string;
  submissions: PublicSubmission[];
  badges: Badge[];
}

// ============ Extended Topic Types with Questions ============

export interface TopicWithQuestions extends Topic {
  questions?: KnowledgeQuestion[];
}

export interface TopicWithProgressAndQuestions extends TopicWithProgress {
  questions?: KnowledgeQuestion[];
  questionsStatus?: TopicQuestionsStatus;
  isUnlocked: boolean;
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

// ============ Hands-On Types (from new API) ============

// These match the API schemas for phase detail
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
