/**
 * React Query hooks for API data fetching.
 * These hooks handle caching, loading states, and error handling.
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '@clerk/clerk-react';
import { createApiClient } from './api-client';

const STALE_TIME_MS = 30_000;

// Create a hook that provides the API client
export function useApi() {
  const { getToken } = useAuth();
  return createApiClient(getToken);
}

export function useDashboard() {
  const api = useApi();
  return useQuery({
    queryKey: ['dashboard'],
    queryFn: () => api.getDashboard(),
    staleTime: STALE_TIME_MS,
  });
}

export function useUserInfo() {
  const api = useApi();
  const { isSignedIn } = useAuth();
  return useQuery({
    queryKey: ['userInfo'],
    queryFn: () => api.getUserInfo(),
    enabled: !!isSignedIn,
    staleTime: STALE_TIME_MS,
  });
}

export function usePhasesWithProgress() {
  const api = useApi();
  return useQuery({
    queryKey: ['phases'],
    queryFn: () => api.getPhasesWithProgress(),
    staleTime: STALE_TIME_MS,
  });
}

export function useBadgeCatalog() {
  const api = useApi();
  return useQuery({
    queryKey: ['badgeCatalog'],
    queryFn: () => api.getBadgeCatalog(),
    staleTime: 5 * 60 * 1000,
  });
}

export function usePhaseDetail(phaseSlug: string) {
  const api = useApi();
  return useQuery({
    queryKey: ['phase', phaseSlug],
    queryFn: () => api.getPhaseDetail(phaseSlug),
    enabled: !!phaseSlug,
    staleTime: STALE_TIME_MS,
  });
}

export function useTopicDetail(phaseSlug: string, topicSlug: string) {
  const api = useApi();
  return useQuery({
    queryKey: ['topic', phaseSlug, topicSlug],
    queryFn: () => api.getTopicDetail(phaseSlug, topicSlug),
    enabled: !!phaseSlug && !!topicSlug,
    staleTime: STALE_TIME_MS,
  });
}

export function useSubmitGitHubUrl() {
  const api = useApi();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ requirementId, url }: { requirementId: string; url: string }) =>
      api.submitGitHubUrl(requirementId, url),
    onSuccess: () => {
      // Invalidate related queries
      queryClient.invalidateQueries({ queryKey: ['dashboard'] });
      queryClient.invalidateQueries({ queryKey: ['phase'] });
      queryClient.invalidateQueries({ queryKey: ['topic'] });
    },
  });
}

export function useCompleteStep() {
  const api = useApi();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      topicId,
      stepOrder,
    }: {
      topicId: string;
      stepOrder: number;
    }) => api.completeStep(topicId, stepOrder),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['dashboard'] });
      queryClient.invalidateQueries({ queryKey: ['phase'] });
      queryClient.invalidateQueries({ queryKey: ['streak'] });
      queryClient.invalidateQueries({ queryKey: ['topic'] });
    },
  });
}

export function useUncompleteStep() {
  const api = useApi();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      topicId,
      stepOrder,
    }: {
      topicId: string;
      stepOrder: number;
    }) => api.uncompleteStep(topicId, stepOrder),
    onSuccess: () => {
      // Invalidate cached step progress so navigation shows fresh data
      queryClient.invalidateQueries({ queryKey: ['dashboard'] });
      queryClient.invalidateQueries({ queryKey: ['phase'] });
      queryClient.invalidateQueries({ queryKey: ['streak'] });
      queryClient.invalidateQueries({ queryKey: ['topic'] });
    },
  });
}

export function useSubmitQuestionAnswer() {
  const api = useApi();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      topicId,
      questionId,
      answer,
      scenarioContext,
    }: {
      topicId: string;
      questionId: string;
      answer: string;
      scenarioContext?: string;
    }) => api.submitAnswer(topicId, questionId, answer, scenarioContext),
    onSuccess: (result) => {
      // Only invalidate caches if the answer was correct
      if (result.is_passed) {
        queryClient.invalidateQueries({ queryKey: ['dashboard'] });
        queryClient.invalidateQueries({ queryKey: ['phase'] });
        queryClient.invalidateQueries({ queryKey: ['streak'] });
        queryClient.invalidateQueries({ queryKey: ['topic'] });
      }
    },
  });
}

export function useStreak() {
  const api = useApi();
  return useQuery({
    queryKey: ['streak'],
    queryFn: () => api.getStreak(),
    staleTime: STALE_TIME_MS,
  });
}

export function usePublicProfile(username: string) {
  const api = useApi();
  return useQuery({
    queryKey: ['publicProfile', username],
    queryFn: () => api.getPublicProfile(username),
    enabled: !!username,
    staleTime: STALE_TIME_MS,
  });
}

export function useCertificateEligibility(certificateType: string) {
  const api = useApi();
  return useQuery({
    queryKey: ['certificateEligibility', certificateType],
    queryFn: () => api.getCertificateEligibility(certificateType),
    enabled: !!certificateType,
    staleTime: STALE_TIME_MS,
  });
}

export function useGenerateCertificate() {
  const api = useApi();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ certificateType, recipientName }: { certificateType: string; recipientName: string }) =>
      api.generateCertificate(certificateType, recipientName),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['userCertificates'] });
      queryClient.invalidateQueries({ queryKey: ['certificateEligibility'] });
    },
  });
}

export function useUserCertificates() {
  const api = useApi();
  return useQuery({
    queryKey: ['userCertificates'],
    queryFn: () => api.getUserCertificates(),
    staleTime: STALE_TIME_MS,
  });
}

export function useVerifyCertificate(code: string) {
  const api = useApi();
  return useQuery({
    queryKey: ['verifyCertificate', code],
    queryFn: () => api.verifyCertificate(code),
    enabled: !!code,
    staleTime: STALE_TIME_MS,
  });
}
