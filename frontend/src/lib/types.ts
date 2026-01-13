/* API types matching backend schemas */

export type CompletionStatus = 'not_started' | 'in_progress' | 'completed';

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
}

export interface TopicChecklistItem {
  id: string;
  text: string;
  order: number;
}

export interface TopicChecklistItemWithProgress extends TopicChecklistItem {
  is_completed: boolean;
  completed_at: string | null;
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
  checklist: TopicChecklistItem[];
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
  checklist: TopicChecklistItemWithProgress[];
  questions?: KnowledgeQuestion[];
  is_capstone: boolean;
  items_completed: number;
  items_total: number;
}

export interface ChecklistItem {
  id: string;
  text: string;
  order: number;
}

export interface ChecklistItemWithProgress extends ChecklistItem {
  is_completed: boolean;
  completed_at: string | null;
}

export interface PhaseProgress {
  phase_id: number;
  checklist_completed: number;
  checklist_total: number;
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
  total_completed: number;
  total_items: number;
  current_phase: number | null;
}

// ============ GitHub Submission Types ============

export type SubmissionType = 'profile_readme' | 'repo_fork' | 'deployed_app';

export interface GitHubRequirement {
  id: string;
  phase_id: number;
  submission_type: SubmissionType;
  name: string;
  description: string;
  example_url: string | null;
  required_repo: string | null;
  expected_endpoint: string | null;
}

export interface GitHubSubmission {
  id: number;
  requirement_id: string;
  submission_type: string;
  phase_id: number;
  submitted_url: string;
  github_username: string | null;
  is_validated: boolean;
  validated_at: string | null;
  created_at: string;
}

export interface GitHubValidationResult {
  is_valid: boolean;
  message: string;
  username_match: boolean;
  repo_exists: boolean;
  submission: GitHubSubmission | null;
}

export interface PhaseGitHubRequirements {
  phase_id: number;
  requirements: GitHubRequirement[];
  submissions: GitHubSubmission[];
  has_requirements: boolean;  // False if phase has no requirements defined
  all_validated: boolean;
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

// ============ Reflection & Activity Types ============

export interface ReflectionResponse {
  id: number;
  reflection_date: string;
  reflection_text: string;
  ai_greeting: string | null;
  created_at: string;
}

export interface LatestGreetingResponse {
  has_greeting: boolean;
  greeting: string | null;
  reflection_date: string | null;
  user_first_name: string | null;
}

export interface StreakResponse {
  current_streak: number;
  longest_streak: number;
  total_activity_days: number;
  last_activity_date: string | null;
  streak_alive: boolean;
}

export type ActivityType = 'question_attempt' | 'topic_complete' | 'reflection' | 'certificate_earned';

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
  submitted_url: string;
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
  completed_topics: number;
  total_topics: number;
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
  topics_completed: number;
  total_topics: number;
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
  topics_completed: number;
  total_topics: number;
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
