/* API types matching backend schemas */

export type CompletionStatus = 'not_started' | 'in_progress' | 'completed';

export interface LearningStep {
  order: number;
  text: string;
  url: string;
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
  estimated_weeks: string;
  order: number;
  prerequisites: string[];
  topics: Topic[];
  checklist: ChecklistItem[];
}

export interface PhaseWithProgress extends Phase {
  progress: PhaseProgress | null;
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
  checklist: ChecklistItemWithProgress[];
  progress: PhaseProgress | null;
}

export interface User {
  id: string;
  email: string;
  first_name: string | null;
  last_name: string | null;
  avatar_url: string | null;
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
