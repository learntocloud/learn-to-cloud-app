/**
 * React Query hooks for API data fetching.
 * These hooks handle caching, loading states, and error handling.
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '@clerk/clerk-react';
import { createApiClient } from './api-client';

// Create a hook that provides the API client
function useApi() {
  const { getToken } = useAuth();
  return createApiClient(getToken);
}

export function useDashboard() {
  const api = useApi();
  return useQuery({
    queryKey: ['dashboard'],
    queryFn: () => api.getDashboard(),
  });
}

export function useUserInfo() {
  const api = useApi();
  return useQuery({
    queryKey: ['userInfo'],
    queryFn: () => api.getUserInfo(),
  });
}

export function usePhasesWithProgress() {
  const api = useApi();
  return useQuery({
    queryKey: ['phases'],
    queryFn: () => api.getPhasesWithProgress(),
  });
}

export function usePhaseDetail(phaseSlug: string) {
  const api = useApi();
  return useQuery({
    queryKey: ['phase', phaseSlug],
    queryFn: () => api.getPhaseDetail(phaseSlug),
    enabled: !!phaseSlug,
  });
}

export function useTopicDetail(phaseSlug: string, topicSlug: string) {
  const api = useApi();
  return useQuery({
    queryKey: ['topic', phaseSlug, topicSlug],
    queryFn: () => api.getTopicDetail(phaseSlug, topicSlug),
    enabled: !!phaseSlug && !!topicSlug,
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

export function useStreak() {
  const api = useApi();
  return useQuery({
    queryKey: ['streak'],
    queryFn: () => api.getStreak(),
  });
}

export function usePublicProfile(username: string) {
  const api = useApi();
  return useQuery({
    queryKey: ['publicProfile', username],
    queryFn: () => api.getPublicProfile(username),
    enabled: !!username,
  });
}

export function useCertificateEligibility(certificateType: string) {
  const api = useApi();
  return useQuery({
    queryKey: ['certificateEligibility', certificateType],
    queryFn: () => api.getCertificateEligibility(certificateType),
    enabled: !!certificateType,
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
  });
}

export function useVerifyCertificate(code: string) {
  const api = useApi();
  return useQuery({
    queryKey: ['verifyCertificate', code],
    queryFn: () => api.verifyCertificate(code),
    enabled: !!code,
  });
}
