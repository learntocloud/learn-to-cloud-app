/**
 * MSW request handlers for API mocking.
 * Define default handlers that return successful responses.
 * Override in individual tests for error scenarios.
 */

import { http, HttpResponse, delay, type PathParams } from 'msw';

const API_URL = '';

// Mock data types matching backend schemas
interface MockUser {
  id: string;
  email: string;
  first_name: string | null;
  last_name: string | null;
  avatar_url: string | null;
  github_username: string | null;
  is_admin: boolean;
  created_at: string;
}

interface MockPhase {
  id: number;
  slug: string;
  name: string;
  description: string;
  order: number;
  topics: MockTopic[];
  is_locked: boolean;
}

interface MockTopic {
  id: string;
  slug: string;
  name: string;
  description: string;
  order: number;
  is_capstone: boolean;
  steps_count: number;
  progress: {
    steps_completed: number;
    steps_total: number;
    percentage: number;
    status: 'not_started' | 'in_progress' | 'completed';
  } | null;
  is_locked: boolean;
}

// Default mock data
const mockUser: MockUser = {
  id: 'user_test123',
  email: 'test@example.com',
  first_name: 'Test',
  last_name: 'User',
  avatar_url: null,
  github_username: 'testuser',
  is_admin: false,
  created_at: '2025-01-01T00:00:00Z',
};

const mockDashboard = {
  current_phase: 1,
  phases_completed: 0,
  total_phases: 8,
  overall_progress: 10,
  badges: [
    { id: 'phase_0_complete', name: 'Cloud Seedling', description: 'Completed Phase 0', icon: '🌱' },
  ],
};

const mockPhases: MockPhase[] = [
  {
    id: 1,
    slug: 'phase0',
    name: 'Starting from Zero',
    description: 'Build your IT foundation',
    order: 0,
    topics: [
      {
        id: 'topic-1',
        slug: 'cloud-computing',
        name: 'What is Cloud Computing?',
        description: 'Learn the basics',
        order: 0,
        is_capstone: false,
        steps_count: 5,
        progress: null,
        is_locked: false,
      },
    ],
    is_locked: false,
  },
  {
    id: 2,
    slug: 'phase1',
    name: 'Linux and Bash',
    description: 'Master the command line',
    order: 1,
    topics: [],
    is_locked: true,
  },
];

const mockBadgeCatalog = {
  phase_badges: [
    {
      id: 'phase_0_complete',
      name: 'Cloud Seedling',
      description: 'Completed Phase 0',
      icon: '🌱',
      num: '#001',
      how_to: 'Complete Phase 0: Starting from Zero',
      phase_id: 0,
      phase_name: 'Starting from Zero',
    },
  ],
  total_badges: 1,
  phase_themes: [
    {
      phase_id: 0,
      icon: '🌱',
      bg_class: 'bg-gray-50 dark:bg-gray-800/50',
      border_class: 'border-gray-200 dark:border-gray-700',
      text_class: 'text-gray-600 dark:text-gray-400',
    },
  ],
};

export const handlers = [
  // User info
  http.get(`${API_URL}/api/me`, async () => {
    await delay(50);
    return HttpResponse.json(mockUser);
  }),

  // Dashboard
  http.get(`${API_URL}/api/dashboard`, async () => {
    await delay(50);
    return HttpResponse.json(mockDashboard);
  }),

  // Badge catalog
  http.get(`${API_URL}/api/user/badges/catalog`, async () => {
    await delay(50);
    return HttpResponse.json(mockBadgeCatalog);
  }),

  // Phases list
  http.get(`${API_URL}/api/phases`, async () => {
    await delay(50);
    return HttpResponse.json(mockPhases);
  }),

  // Phase detail
  http.get(`${API_URL}/api/phases/:phaseSlug`, async ({ params }: { params: PathParams }) => {
    await delay(50);
    const phase = mockPhases.find((p) => p.slug === params.phaseSlug);
    if (!phase) {
      return HttpResponse.json({ detail: 'Phase not found' }, { status: 404 });
    }
    return HttpResponse.json(phase);
  }),

  // Topic detail
  http.get(`${API_URL}/api/phases/:phaseSlug/topics/:topicSlug`, async ({ params }: { params: PathParams }) => {
    await delay(50);
    const phase = mockPhases.find((p) => p.slug === params.phaseSlug);
    if (!phase) {
      return HttpResponse.json({ detail: 'Phase not found' }, { status: 404 });
    }
    const topic = phase.topics.find((t) => t.slug === params.topicSlug);
    if (!topic) {
      return HttpResponse.json({ detail: 'Topic not found' }, { status: 404 });
    }
    return HttpResponse.json({
      ...topic,
      learning_steps: [
        { order: 1, text: 'Step 1', action: null, title: null, url: null, description: null, code: null, secondary_links: [], options: [] },
      ],
      completed_step_orders: [],
      learning_objectives: [],
      is_locked: false,
      is_topic_locked: false,
    });
  }),

  // Step completion
  http.post(`${API_URL}/api/topics/:topicId/steps/:stepOrder/complete`, async () => {
    await delay(50);
    return HttpResponse.json({
      topic_id: 'topic-1',
      completed_steps: [1],
      total_steps: 5,
      next_unlocked_step: 2,
    });
  }),

  // Public profile
  http.get(`${API_URL}/api/users/:username/profile`, async ({ params }: { params: PathParams }) => {
    await delay(50);
    return HttpResponse.json({
      username: params.username,
      first_name: 'Test',
      avatar_url: null,
      current_phase: 1,
      phases_completed: 0,
      member_since: '2025-01-01T00:00:00Z',
      submissions: [],
      badges: [],
    });
  }),

  // Certificate eligibility
  http.get(`${API_URL}/api/certificates/:certificateType/eligibility`, async ({ params }: { params: PathParams }) => {
    await delay(50);
    return HttpResponse.json({
      is_eligible: false,
      certificate_type: params.certificateType,
      phases_completed: 1,
      total_phases: 7,
      completion_percentage: 14,
      already_issued: false,
      existing_certificate_id: null,
      message: 'Complete all phases to earn this certificate',
    });
  }),

  // User certificates
  http.get(`${API_URL}/api/certificates`, async () => {
    await delay(50);
    return HttpResponse.json({
      certificates: [],
      full_completion_eligible: false,
    });
  }),

  // Verify certificate
  http.get(`${API_URL}/api/certificates/verify/:code`, async ({ params }: { params: PathParams }) => {
    await delay(50);
    if (params.code === 'VALID123') {
      return HttpResponse.json({
        is_valid: true,
        certificate: {
          id: 1,
          certificate_type: 'full_completion',
          verification_code: 'VALID123',
          recipient_name: 'Test User',
          issued_at: '2026-01-15T00:00:00Z',
          phases_completed: 8,
          total_phases: 8,
        },
        message: 'Certificate is valid',
      });
    }
    return HttpResponse.json({
      is_valid: false,
      certificate: null,
      message: 'Invalid certificate code',
    });
  }),
];
