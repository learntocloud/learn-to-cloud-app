import { useState } from 'react';
import { useSubmitGitHubUrl } from '@/lib/hooks';
import type { HandsOnRequirement, HandsOnSubmission, GitHubValidationResult, PhaseProgressSchema } from '@/lib/api-client';

interface PhaseVerificationFormProps {
  phaseNumber: number;
  requirements: HandsOnRequirement[];
  submissions: HandsOnSubmission[];
  githubUsername: string | null;
  nextPhaseSlug?: string;
  phaseProgress?: PhaseProgressSchema | null;
  // Computed values from API - DO NOT recalculate
  allHandsOnValidated: boolean;
  isPhaseComplete: boolean;
}

export function PhaseVerificationForm({
  phaseNumber,
  requirements,
  submissions,
  githubUsername,
  nextPhaseSlug,
  phaseProgress,
  allHandsOnValidated,
  isPhaseComplete,
}: PhaseVerificationFormProps) {
  const [urls, setUrls] = useState<Record<string, string>>({});
  const [validationMessages, setValidationMessages] = useState<Record<string, { message: string; isValid: boolean }>>({});
  const submitMutation = useSubmitGitHubUrl();

  const getSubmissionForRequirement = (reqId: string) => {
    return submissions.find((s) => s.requirement_id === reqId);
  };

  const handleSubmit = async (requirementId: string) => {
    const url = urls[requirementId];
    if (!url) return;

    try {
      const result = await submitMutation.mutateAsync({ requirementId, url }) as GitHubValidationResult;
      setValidationMessages((prev) => ({
        ...prev,
        [requirementId]: { message: result.message, isValid: result.is_valid },
      }));
      setUrls((prev) => ({ ...prev, [requirementId]: '' }));
    } catch (error) {
      setValidationMessages((prev) => ({
        ...prev,
        [requirementId]: { message: error instanceof Error ? error.message : 'Submission failed', isValid: false },
      }));
    }
  };

  // Use API-computed values - business logic lives in API, not frontend
  const stepsAndQuestionsComplete = phaseProgress?.status === 'completed';

  return (
    <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-6">
      <div className="flex items-center gap-3 mb-6">
        <div className="text-3xl">🎯</div>
        <div>
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
            Hands-on Verification
          </h3>
          <p className="text-sm text-gray-500 dark:text-gray-400">
            Submit your GitHub repos to verify your hands-on work
          </p>
        </div>
      </div>

      {!githubUsername && (
        <div className="mb-6 p-4 bg-yellow-50 dark:bg-yellow-900/30 rounded-lg border border-yellow-200 dark:border-yellow-800">
          <p className="text-sm text-yellow-700 dark:text-yellow-300">
            ⚠️ Please connect your GitHub account in your profile settings to submit repos.
          </p>
        </div>
      )}

      <div className="space-y-4">
        {requirements.map((req) => {
          const submission = getSubmissionForRequirement(req.id);
          const isPassed = submission?.is_validated === true;
          const isFailed = submission && !submission.is_validated;
          const validationMsg = validationMessages[req.id];

          return (
            <div
              key={req.id}
              className={`p-4 rounded-lg border ${
                isPassed
                  ? 'bg-emerald-50 dark:bg-emerald-900/20 border-emerald-200 dark:border-emerald-800'
                  : isFailed
                  ? 'bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800'
                  : 'bg-gray-50 dark:bg-gray-900/50 border-gray-200 dark:border-gray-700'
              }`}
            >
              <div className="flex items-start justify-between gap-4">
                <div className="flex-1">
                  <div className="flex items-center gap-2 mb-1">
                    {isPassed && (
                      <svg className="w-5 h-5 text-emerald-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                      </svg>
                    )}
                    {isFailed && (
                      <svg className="w-5 h-5 text-red-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                      </svg>
                    )}
                    <h4 className="font-medium text-gray-900 dark:text-white">{req.name}</h4>
                  </div>
                  <p className="text-sm text-gray-600 dark:text-gray-400">{req.description}</p>
                </div>

                {isPassed && (
                  <span className="px-2 py-1 bg-emerald-100 dark:bg-emerald-900/50 text-emerald-700 dark:text-emerald-300 text-xs rounded-full">
                    Verified
                  </span>
                )}
                {isFailed && (
                  <span className="px-2 py-1 bg-red-100 dark:bg-red-900/50 text-red-700 dark:text-red-300 text-xs rounded-full">
                    Failed
                  </span>
                )}
              </div>

              {/* Show validation message */}
              {validationMsg && (
                <div className={`mt-3 p-3 rounded-lg text-sm ${
                  validationMsg.isValid
                    ? 'bg-emerald-100 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-300'
                    : 'bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-300'
                }`}>
                  {validationMsg.message}
                </div>
              )}

              {!isPassed && githubUsername && (
                <div className="mt-4">
                  {submission?.submitted_value && (
                    <div className="mb-2 text-sm">
                      <span className="text-gray-500 dark:text-gray-400">Submitted: </span>
                      <a
                        href={submission.submitted_value}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-blue-600 dark:text-blue-400 hover:underline"
                      >
                        {submission.submitted_value}
                      </a>
                    </div>
                  )}

                  <div className="flex gap-2">
                    <input
                      type="url"
                      value={urls[req.id] || ''}
                      onChange={(e) => setUrls((prev) => ({ ...prev, [req.id]: e.target.value }))}
                      placeholder="https://github.com/username/repo"
                      className="flex-1 px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                      disabled={submitMutation.isPending}
                    />
                    <button
                      onClick={() => handleSubmit(req.id)}
                      disabled={!urls[req.id] || submitMutation.isPending}
                      className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                    >
                      {submitMutation.isPending ? 'Submitting...' : 'Submit'}
                    </button>
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {isPhaseComplete && nextPhaseSlug && (
        <div className="mt-6 p-4 bg-emerald-50 dark:bg-emerald-900/20 rounded-lg border border-emerald-200 dark:border-emerald-800 text-center">
          <p className="text-emerald-700 dark:text-emerald-300 font-medium mb-3">
            🎉 All verifications complete! Phase {phaseNumber} finished!
          </p>
          <a
            href={`/${nextPhaseSlug}`}
            className="inline-flex items-center px-4 py-2 bg-emerald-600 text-white rounded-lg font-medium hover:bg-emerald-700 transition-colors"
          >
            Continue to Phase {phaseNumber + 1} →
          </a>
        </div>
      )}

      {/* Show hands-on complete but steps/questions incomplete */}
      {allHandsOnValidated && !stepsAndQuestionsComplete && (
        <div className="mt-6 p-4 bg-amber-50 dark:bg-amber-900/20 rounded-lg border border-amber-200 dark:border-amber-800 text-center">
          <p className="text-amber-700 dark:text-amber-300 font-medium">
            ✅ All hands-on requirements verified! Complete all learning steps and questions to finish Phase {phaseNumber}.
          </p>
        </div>
      )}
    </div>
  );
}
