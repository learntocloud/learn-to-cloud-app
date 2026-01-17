import { describe, it, expect, beforeEach, vi } from 'vitest';
import { createApiClient } from './api-client';

// Mock environment variable
vi.stubEnv('VITE_API_URL', 'http://localhost:8000');

describe('API Client', () => {
  let mockGetToken: ReturnType<typeof vi.fn<[], Promise<string | null>>>;
  let mockFetch: ReturnType<
    typeof vi.fn<Parameters<typeof fetch>, ReturnType<typeof fetch>>
  >;

  const makeResponse = (response: Partial<Response> & { ok: boolean }) =>
    response as Response;

  beforeEach(() => {
    // Reset mocks before each test
    mockGetToken = vi.fn<[], Promise<string | null>>();
    mockFetch = vi.fn<Parameters<typeof fetch>, ReturnType<typeof fetch>>();
    global.fetch = mockFetch as typeof fetch;
  });

  describe('getUserInfo', () => {
    it('fetches user info successfully', async () => {
      const mockUserInfo = {
        id: '123',
        email: 'test@example.com',
        first_name: 'Test',
        last_name: 'User',
        avatar_url: 'https://example.com/avatar.jpg',
        github_username: 'testuser',
        is_admin: false,
        created_at: '2024-01-01T00:00:00Z',
      };

      mockGetToken.mockResolvedValue('mock-token');
      mockFetch.mockResolvedValue(
        makeResponse({
          ok: true,
          json: async () => mockUserInfo,
        })
      );

      const client = createApiClient(mockGetToken);
      const result = await client.getUserInfo();

      expect(result).toEqual(mockUserInfo);
      expect(mockFetch).toHaveBeenCalledWith(
        'http://localhost:8000/api/user/me',
        expect.objectContaining({
          headers: expect.objectContaining({
            'Content-Type': 'application/json',
            'Authorization': 'Bearer mock-token',
          }),
        })
      );
    });

    it('throws error when fetch fails', async () => {
      mockGetToken.mockResolvedValue('mock-token');
      mockFetch.mockResolvedValue(
        makeResponse({
          ok: false,
          status: 500,
        })
      );

      const client = createApiClient(mockGetToken);

      await expect(client.getUserInfo()).rejects.toThrow('Failed to fetch user info');
    });

    it('fetches without auth token when not provided', async () => {
      mockGetToken.mockResolvedValue(null);
      mockFetch.mockResolvedValue(
        makeResponse({
          ok: true,
          json: async () => ({}),
        })
      );

      const client = createApiClient(mockGetToken);
      await client.getUserInfo();

      expect(mockFetch).toHaveBeenCalledWith(
        'http://localhost:8000/api/user/me',
        expect.objectContaining({
          headers: expect.not.objectContaining({
            'Authorization': expect.anything(),
          }),
        })
      );
    });
  });

  describe('getDashboard', () => {
    it('fetches dashboard data successfully', async () => {
      const mockDashboard = {
        user: {
          id: '123',
          email: 'test@example.com',
          first_name: 'Test',
          last_name: 'User',
          avatar_url: null,
          github_username: 'testuser',
          is_admin: false,
        },
        phases: [],
        overall_progress: 25,
        phases_completed: 1,
        phases_total: 4,
        current_phase: 2,
        badges: [],
      };

      mockGetToken.mockResolvedValue('mock-token');
      mockFetch.mockResolvedValue(
        makeResponse({
          ok: true,
          json: async () => mockDashboard,
        })
      );

      const client = createApiClient(mockGetToken);
      const result = await client.getDashboard();

      expect(result).toEqual(mockDashboard);
      expect(mockFetch).toHaveBeenCalledWith(
        'http://localhost:8000/api/user/dashboard',
        expect.any(Object)
      );
    });
  });

  describe('completeStep', () => {
    it('completes a step successfully', async () => {
      const mockStepProgress = {
        topic_id: 'topic-123',
        completed_steps: [1],
        total_steps: 5,
        next_unlocked_step: 2,
      };

      mockGetToken.mockResolvedValue('mock-token');
      // Mock both the complete call and the subsequent getTopicStepProgress call
      mockFetch
        .mockResolvedValueOnce(
          makeResponse({
            ok: true,
            json: async () => ({ success: true }),
          })
        )
        .mockResolvedValueOnce(
          makeResponse({
            ok: true,
            json: async () => mockStepProgress,
          })
        );

      const client = createApiClient(mockGetToken);
      const result = await client.completeStep('topic-123', 1);

      expect(result).toEqual(mockStepProgress);

      // Verify the complete step call
      expect(mockFetch).toHaveBeenCalledWith(
        'http://localhost:8000/api/steps/complete',
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({ topic_id: 'topic-123', step_order: 1 }),
        })
      );

      // Verify the get topic progress call
      expect(mockFetch).toHaveBeenCalledWith(
        'http://localhost:8000/api/steps/topic-123',
        expect.any(Object)
      );
    });
  });

  describe('submitGitHubUrl', () => {
    it('submits GitHub URL successfully', async () => {
      const mockValidation = {
        is_valid: true,
        message: 'Repository validated successfully',
      };

      mockGetToken.mockResolvedValue('mock-token');
      mockFetch.mockResolvedValue(
        makeResponse({
          ok: true,
          json: async () => mockValidation,
        })
      );

      const client = createApiClient(mockGetToken);
      const result = await client.submitGitHubUrl(
        'req-123',
        'https://github.com/user/repo'
      );

      expect(result).toEqual(mockValidation);
      expect(mockFetch).toHaveBeenCalledWith(
        'http://localhost:8000/api/github/submit',
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({
            requirement_id: 'req-123',
            submitted_value: 'https://github.com/user/repo',
          }),
        })
      );
    });

    it('handles validation errors', async () => {
      mockGetToken.mockResolvedValue('mock-token');
      mockFetch.mockResolvedValue(
        makeResponse({
          ok: false,
          json: async () => ({ detail: 'Invalid repository URL' }),
        })
      );

      const client = createApiClient(mockGetToken);

      await expect(
        client.submitGitHubUrl('req-123', 'invalid-url')
      ).rejects.toThrow('Invalid repository URL');
    });
  });

  describe('getPhaseDetail', () => {
    it('returns null for 404 response', async () => {
      mockGetToken.mockResolvedValue('mock-token');
      mockFetch.mockResolvedValue(
        makeResponse({
          ok: false,
          status: 404,
        })
      );

      const client = createApiClient(mockGetToken);
      const result = await client.getPhaseDetail('non-existent');

      expect(result).toBeNull();
    });

    it('throws error for non-404 failures', async () => {
      mockGetToken.mockResolvedValue('mock-token');
      mockFetch.mockResolvedValue(
        makeResponse({
          ok: false,
          status: 500,
        })
      );

      const client = createApiClient(mockGetToken);

      await expect(client.getPhaseDetail('phase-1')).rejects.toThrow(
        'Failed to fetch phase'
      );
    });
  });
});
