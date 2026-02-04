/**
 * Tests for custom React Query hooks.
 * Note: These hooks depend on Clerk authentication and the API client.
 * For simpler unit testing, we test the hook behaviors that don't require
 * full API integration.
 */

import { describe, it, expect, vi } from 'vitest';
import { renderHook } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ReactNode } from 'react';

// Mock the entire api-client module
vi.mock('./api-client', () => ({
  createApiClient: vi.fn(() => ({
    getDashboard: vi.fn().mockResolvedValue({
      current_phase: 1,
      phases_completed: 0,
      total_phases: 8,
      overall_progress: 10,
    }),
    getPhasesWithProgress: vi.fn().mockResolvedValue([
      { id: 1, slug: 'phase0', name: 'Phase 0', is_locked: false },
    ]),
    getUserInfo: vi.fn().mockResolvedValue({
      id: 'user_123',
      email: 'test@example.com',
      github_username: 'testuser',
    }),
  })),
}));

// Mock Clerk's useAuth hook
vi.mock('@clerk/clerk-react', () => ({
  useAuth: vi.fn(() => ({
    getToken: vi.fn().mockResolvedValue('mock-token'),
    isSignedIn: true,
  })),
}));

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        gcTime: 0,
      },
    },
  });

  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>
        {children}
      </QueryClientProvider>
    );
  };
}

// Import hooks after setting up mocks
import { useDashboard, usePhasesWithProgress } from './hooks';

describe('useDashboard', () => {
  it('initializes with loading state', () => {
    const { result } = renderHook(() => useDashboard(), {
      wrapper: createWrapper(),
    });

    expect(result.current.isPending || result.current.isLoading).toBe(true);
  });

  it('returns query result structure', () => {
    const { result } = renderHook(() => useDashboard(), {
      wrapper: createWrapper(),
    });

    expect(result.current).toHaveProperty('data');
    expect(result.current).toHaveProperty('isLoading');
    expect(result.current).toHaveProperty('refetch');
  });
});

describe('usePhasesWithProgress', () => {
  it('initializes with loading state', () => {
    const { result } = renderHook(() => usePhasesWithProgress(), {
      wrapper: createWrapper(),
    });

    expect(result.current.isPending || result.current.isLoading).toBe(true);
  });

  it('returns query result structure', () => {
    const { result } = renderHook(() => usePhasesWithProgress(), {
      wrapper: createWrapper(),
    });

    expect(result.current).toHaveProperty('data');
    expect(result.current).toHaveProperty('isLoading');
    expect(result.current).toHaveProperty('isError');
  });
});
