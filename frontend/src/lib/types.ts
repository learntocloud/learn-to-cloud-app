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
