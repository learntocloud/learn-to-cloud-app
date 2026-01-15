/**
 * GitHub Submission Form component for Vite SPA.
 * Handles hands-on verification by submitting GitHub URLs.
 */

import { useState, useEffect } from "react";
import { useApiClient } from "@/lib/hooks";
import type { HandsOnRequirement, HandsOnSubmission, GitHubValidationResult } from "@/lib/types";

interface GitHubSubmissionFormProps {
  requirements: HandsOnRequirement[];
  submissions: HandsOnSubmission[];
  githubUsername: string | null;
  onSubmissionSuccess?: () => void;
  onAllVerificationsComplete?: () => void;
}

// Check if requirements should share a single URL input
function shouldUseSharedUrl(requirements: HandsOnRequirement[]): boolean {
  const repoRequirements = requirements.filter(
    (r) => r.submission_type !== 'container_image'
  );

  if (repoRequirements.length <= 1) return false;

  const shareableTypes = new Set(['repo_with_files', 'workflow_run', 'repo_url', 'repo_fork']);
  const allShareable = repoRequirements.every((r) => shareableTypes.has(r.submission_type));
  if (!allShareable) return false;

  const phases = new Set(repoRequirements.map((r) => r.phase_id));
  return phases.size === 1;
}

function getRepoRequirements(requirements: HandsOnRequirement[]): HandsOnRequirement[] {
  return requirements.filter((r) => r.submission_type !== 'container_image');
}

function getContainerImageRequirements(requirements: HandsOnRequirement[]): HandsOnRequirement[] {
  return requirements.filter((r) => r.submission_type === 'container_image');
}

export function GitHubSubmissionForm({
  requirements,
  submissions,
  githubUsername,
  onSubmissionSuccess,
  onAllVerificationsComplete,
}: GitHubSubmissionFormProps) {
  const api = useApiClient();
  const useSharedUrl = shouldUseSharedUrl(requirements);

  const [urls, setUrls] = useState<Record<string, string>>(() => {
    const initial: Record<string, string> = {};
    for (const sub of submissions) {
      initial[sub.requirement_id] = sub.submitted_value;
    }
    return initial;
  });

  const [sharedUrl, setSharedUrl] = useState<string>(() => {
    const existingSub = submissions.find((s) => s.submitted_value);
    return existingSub?.submitted_value || "";
  });

  const [loading, setLoading] = useState<Record<string, boolean>>({});
  const [results, setResults] = useState<Record<string, GitHubValidationResult | null>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [sharedError, setSharedError] = useState<string>("");
  const [hasCelebratedCompletion, setHasCelebratedCompletion] = useState(false);
  const [isVerifyingAll, setIsVerifyingAll] = useState(false);

  // Check if all verifications are already complete on mount
  useEffect(() => {
    if (hasCelebratedCompletion || !onAllVerificationsComplete) return;

    const allAlreadyValidated = requirements.every((req) => {
      const existingSub = submissions.find((s) => s.requirement_id === req.id);
      return existingSub?.is_validated;
    });

    if (allAlreadyValidated && requirements.length > 0) {
      setHasCelebratedCompletion(true);
    }
  }, [requirements, submissions, onAllVerificationsComplete, hasCelebratedCompletion]);

  const getSubmissionForRequirement = (requirementId: string): HandsOnSubmission | undefined => {
    return submissions.find((s) => s.requirement_id === requirementId);
  };

  const handleSubmit = async (requirementId: string) => {
    if (!api) return;

    const url = urls[requirementId]?.trim();
    if (!url) {
      setErrors((prev) => ({ ...prev, [requirementId]: "Please enter a URL" }));
      return;
    }

    setLoading((prev) => ({ ...prev, [requirementId]: true }));
    setErrors((prev) => ({ ...prev, [requirementId]: "" }));
    setResults((prev) => ({ ...prev, [requirementId]: null }));

    try {
      const data = await api.submitGitHubUrl(requirementId, url);

      setResults((prev) => {
        const newResults = { ...prev, [requirementId]: data };

        if (data.is_valid && onAllVerificationsComplete) {
          const allValidated = requirements.every((req) => {
            const existingSub = submissions.find((s) => s.requirement_id === req.id);
            const result = newResults[req.id];
            return existingSub?.is_validated || result?.is_valid;
          });

          if (allValidated && !hasCelebratedCompletion) {
            setHasCelebratedCompletion(true);
            setTimeout(() => onAllVerificationsComplete(), 500);
          }
        }

        return newResults;
      });

      if (data.is_valid && onSubmissionSuccess) {
        onSubmissionSuccess();
      }
    } catch (err) {
      setErrors((prev) => ({
        ...prev,
        [requirementId]: err instanceof Error ? err.message : "Network error. Please try again.",
      }));
    } finally {
      setLoading((prev) => ({ ...prev, [requirementId]: false }));
    }
  };

  const handleVerifyAll = async () => {
    if (!api) return;

    const url = sharedUrl.trim();
    if (!url) {
      setSharedError("Please enter a repository URL");
      return;
    }

    setIsVerifyingAll(true);
    setSharedError("");

    const repoReqs = getRepoRequirements(requirements);

    const clearedResults: Record<string, GitHubValidationResult | null> = { ...results };
    const clearedErrors: Record<string, string> = { ...errors };
    for (const req of repoReqs) {
      clearedResults[req.id] = null;
      clearedErrors[req.id] = "";
    }
    setResults(clearedResults);
    setErrors(clearedErrors);

    const loadingState: Record<string, boolean> = {};
    for (const req of repoReqs) {
      loadingState[req.id] = true;
    }
    setLoading(loadingState);

    let allPassed = true;
    const newResults: Record<string, GitHubValidationResult | null> = {};

    for (const req of repoReqs) {
      try {
        const data = await api.submitGitHubUrl(req.id, url);
        newResults[req.id] = data;
        setResults((prev) => ({ ...prev, [req.id]: data }));
        if (!data.is_valid) {
          allPassed = false;
        }
      } catch (err) {
        setErrors((prev) => ({
          ...prev,
          [req.id]: err instanceof Error ? err.message : "Network error",
        }));
        allPassed = false;
      } finally {
        setLoading((prev) => ({ ...prev, [req.id]: false }));
      }
    }

    setIsVerifyingAll(false);

    if (allPassed && onAllVerificationsComplete && !hasCelebratedCompletion) {
      const allValidated = requirements.every((req) => {
        const existingSub = submissions.find((s) => s.requirement_id === req.id);
        const result = newResults[req.id] || results[req.id];
        return existingSub?.is_validated || result?.is_valid;
      });

      if (allValidated) {
        setHasCelebratedCompletion(true);
        setTimeout(() => onAllVerificationsComplete(), 500);
      }
    }
  };

  // Check if any requirements need GitHub username
  const hasGitHubRequirements = requirements.some(
    (r) => r.submission_type === "profile_readme" || r.submission_type === "repo_fork"
  );

  if (!githubUsername && hasGitHubRequirements) {
    return (
      <div className="bg-yellow-50 dark:bg-yellow-900/30 rounded-lg border border-yellow-200 dark:border-yellow-800 p-6">
        <h3 className="text-lg font-semibold text-yellow-800 dark:text-yellow-200 mb-2">
          ⚠️ GitHub Account Required
        </h3>
        <p className="text-yellow-700 dark:text-yellow-300 mb-4">
          To submit your hands-on work, you need to sign in with GitHub. Please sign out and sign back in using your GitHub account.
        </p>
        <p className="text-sm text-yellow-600 dark:text-yellow-400">
          This allows us to verify that the GitHub repositories you submit actually belong to you.
        </p>
      </div>
    );
  }

  if (requirements.length === 0) {
    return null;
  }

  const repoRequirements = getRepoRequirements(requirements);
  const containerRequirements = getContainerImageRequirements(requirements);

  // Render a single requirement form
  const renderRequirementForm = (req: HandsOnRequirement) => {
    const existingSubmission = getSubmissionForRequirement(req.id);
    const result = results[req.id];
    const error = errors[req.id];
    const isLoading = loading[req.id];
    const isValidated = existingSubmission?.is_validated || result?.is_valid;

    return (
      <div key={req.id} className="p-4 bg-gray-50 dark:bg-gray-700/50 rounded-lg border border-gray-200 dark:border-gray-600">
        <div className="flex items-center gap-2 mb-2">
          {isValidated ? (
            <span className="text-green-600 dark:text-green-400 text-lg">✓</span>
          ) : (
            <span className="text-gray-400 text-lg">○</span>
          )}
          <label className="text-sm font-medium text-gray-700 dark:text-gray-300">
            {req.name}
            {isValidated && <span className="ml-2 text-green-600 dark:text-green-400 text-xs">Verified</span>}
          </label>
        </div>
        <p className="text-xs text-gray-500 dark:text-gray-400 mb-3 ml-6">{req.description}</p>

        {!isValidated && (
          <div className="flex gap-2 ml-6">
            <input
              type="text"
              placeholder={req.example_url || "https://github.com/username/repo"}
              value={urls[req.id] || ""}
              onChange={(e) => setUrls((prev) => ({ ...prev, [req.id]: e.target.value }))}
              disabled={isLoading}
              className="flex-1 px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50"
            />
            <button
              onClick={() => handleSubmit(req.id)}
              disabled={isLoading || !urls[req.id]?.trim()}
              className="px-4 py-2 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 rounded-lg disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {isLoading ? "Verifying..." : "Verify"}
            </button>
          </div>
        )}

        {error && (
          <p className="text-red-600 dark:text-red-400 text-sm mt-2 ml-6">{error}</p>
        )}

        {result && !result.is_valid && result.message && (
          <div className="mt-2 ml-6 p-2 bg-red-50 dark:bg-red-900/20 rounded text-sm text-red-700 dark:text-red-300">
            {result.message}
          </div>
        )}

        {isValidated && existingSubmission && (
          <p className="text-gray-500 dark:text-gray-400 text-xs mt-2 ml-6">
            Submitted: {existingSubmission.submitted_value}
          </p>
        )}
      </div>
    );
  };

  // For shared URL mode
  if (useSharedUrl) {
    const repoAllValidated = repoRequirements.every((req) => {
      const existingSub = getSubmissionForRequirement(req.id);
      const result = results[req.id];
      return existingSub?.is_validated || result?.is_valid;
    });

    return (
      <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-6">
        <h3 className="text-lg font-bold text-gray-900 dark:text-white mb-2">
          🔗 Hands-On Verification
        </h3>
        <p className="text-sm text-gray-600 dark:text-gray-300 mb-4">
          Complete all verifications below to finish this phase.
        </p>

        {/* Shared URL input for repo requirements */}
        {repoRequirements.length > 0 && (
          <div className="mb-6 p-4 bg-gray-50 dark:bg-gray-700/50 rounded-lg border border-gray-200 dark:border-gray-600">
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              Repository URL
            </label>
            <div className="flex gap-2 mb-4">
              <input
                type="text"
                placeholder="https://github.com/username/repository"
                value={sharedUrl}
                onChange={(e) => {
                  setSharedUrl(e.target.value);
                  setSharedError("");
                }}
                disabled={isVerifyingAll || repoAllValidated}
                className="flex-1 px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50"
              />
              {!repoAllValidated && (
                <button
                  onClick={handleVerifyAll}
                  disabled={isVerifyingAll || !sharedUrl.trim()}
                  className="px-4 py-2 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 rounded-lg disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                >
                  {isVerifyingAll ? "Verifying..." : "Verify All"}
                </button>
              )}
            </div>

            {sharedError && (
              <p className="text-red-600 dark:text-red-400 text-sm mb-4">{sharedError}</p>
            )}

            {/* Show status for each repo requirement */}
            <div className="space-y-2">
              {repoRequirements.map((req) => {
                const existingSub = getSubmissionForRequirement(req.id);
                const result = results[req.id];
                const error = errors[req.id];
                const isLoading = loading[req.id];
                const isValidated = existingSub?.is_validated || result?.is_valid;

                return (
                  <div key={req.id} className="flex items-center gap-2 text-sm">
                    {isLoading ? (
                      <svg className="animate-spin w-4 h-4 text-blue-500" viewBox="0 0 24 24">
                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                      </svg>
                    ) : isValidated ? (
                      <span className="text-green-500">✓</span>
                    ) : error || (result && !result.is_valid) ? (
                      <span className="text-red-500">✗</span>
                    ) : (
                      <span className="text-gray-400">○</span>
                    )}
                    <span className={isValidated ? "text-green-700 dark:text-green-300" : "text-gray-700 dark:text-gray-300"}>
                      {req.name}
                    </span>
                    {error && <span className="text-red-500 text-xs ml-2">{error}</span>}
                    {result && !result.is_valid && result.message && (
                      <span className="text-red-500 text-xs ml-2">{result.message}</span>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* Container image requirements need separate inputs */}
        {containerRequirements.length > 0 && (
          <div className="space-y-4">
            {containerRequirements.map(renderRequirementForm)}
          </div>
        )}
      </div>
    );
  }

  // Standard mode: separate input for each requirement
  return (
    <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-6">
      <h3 className="text-lg font-bold text-gray-900 dark:text-white mb-2">
        🔗 Hands-On Verification
      </h3>
      <p className="text-sm text-gray-600 dark:text-gray-300 mb-4">
        Submit your work below for verification.
      </p>

      <div className="space-y-4">
        {requirements.map(renderRequirementForm)}
      </div>
    </div>
  );
}
