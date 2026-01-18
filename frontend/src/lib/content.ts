/**
 * Content loader for static content served from CDN.
 *
 * This module loads phase and topic content from /content/ (served by Azure SWA CDN).
 * The API only returns user progress data; content is loaded locally for performance.
 *
 * Content structure:
 *   /content/phase0/index.json - Phase metadata
 *   /content/phase0/cloud-computing.json - Topic content
 */

// Phase slugs in order
export const PHASE_SLUGS = [
  'phase0',
  'phase1',
  'phase2',
  'phase3',
  'phase4',
  'phase5',
  'phase6',
] as const;

export type PhaseSlug = (typeof PHASE_SLUGS)[number];

// Content types (matching the JSON structure)
export interface ContentSecondaryLink {
  text: string;
  url: string;
}

export interface ContentProviderOption {
  provider: string;
  title: string;
  url: string;
  description: string | null;
}

export interface ContentLearningStep {
  order: number;
  text: string;
  action: string | null;
  title: string | null;
  url: string | null;
  description: string | null;
  code: string | null;
  secondary_links?: ContentSecondaryLink[];
  options?: ContentProviderOption[];
}

export interface ContentQuestion {
  id: string;
  prompt: string;
  // Note: expected_concepts is NOT included - stored server-side for security
}

export interface ContentLearningObjective {
  id: string;
  text: string;
  order: number;
}

export interface ContentTopic {
  id: string;
  slug: string;
  name: string;
  description: string;
  order: number;
  estimated_time: string;
  is_capstone: boolean;
  learning_steps: ContentLearningStep[];
  questions: ContentQuestion[];
  learning_objectives?: ContentLearningObjective[];
  test_knowledge_prompts?: string[];
}

export interface ContentCapstoneOverview {
  title: string;
  summary: string;
  includes?: string[];
  topic_slug?: string;
}

export interface ContentHandsOnOverview {
  summary: string;
  includes?: string[];
}

export interface ContentPhaseIndex {
  id: number;
  name: string;
  slug: string;
  description: string;
  short_description: string;
  estimated_weeks: string;
  order: number;
  objectives: string[];
  capstone?: ContentCapstoneOverview;
  hands_on_verification?: ContentHandsOnOverview;
  topics: string[]; // topic slugs
}

// Cache for loaded content
const contentCache = new Map<string, unknown>();

/**
 * Fetch JSON content from the CDN with caching.
 */
async function fetchContent<T>(path: string): Promise<T> {
  const cacheKey = path;

  if (contentCache.has(cacheKey)) {
    return contentCache.get(cacheKey) as T;
  }

  const response = await fetch(`/content/${path}`);
  if (!response.ok) {
    throw new Error(`Failed to load content: ${path} (${response.status})`);
  }

  const data = await response.json();
  contentCache.set(cacheKey, data);
  return data as T;
}

/**
 * Load phase index (metadata without full topic content).
 */
export async function loadPhaseIndex(phaseSlug: PhaseSlug): Promise<ContentPhaseIndex> {
  return fetchContent<ContentPhaseIndex>(`${phaseSlug}/index.json`);
}

/**
 * Load all phase indices.
 */
export async function loadAllPhaseIndices(): Promise<ContentPhaseIndex[]> {
  const phases = await Promise.all(
    PHASE_SLUGS.map((slug) => loadPhaseIndex(slug))
  );
  return phases;
}

/**
 * Load a single topic's full content.
 */
export async function loadTopic(
  phaseSlug: PhaseSlug,
  topicSlug: string
): Promise<ContentTopic> {
  return fetchContent<ContentTopic>(`${phaseSlug}/${topicSlug}.json`);
}

/**
 * Load all topics for a phase.
 */
export async function loadPhaseTopics(phaseSlug: PhaseSlug): Promise<ContentTopic[]> {
  const index = await loadPhaseIndex(phaseSlug);
  const topics = await Promise.all(
    index.topics.map((topicSlug) => loadTopic(phaseSlug, topicSlug))
  );
  return topics.sort((a, b) => a.order - b.order);
}

/**
 * Preload content for a phase (useful for prefetching).
 */
export async function preloadPhaseContent(phaseSlug: PhaseSlug): Promise<void> {
  await loadPhaseIndex(phaseSlug);
  await loadPhaseTopics(phaseSlug);
}

/**
 * Clear the content cache (useful for testing or forced refresh).
 */
export function clearContentCache(): void {
  contentCache.clear();
}

/**
 * Check if a phase slug is valid.
 */
export function isValidPhaseSlug(slug: string): slug is PhaseSlug {
  return PHASE_SLUGS.includes(slug as PhaseSlug);
}
