import { useState, useEffect, useCallback } from 'react';
import { useSubmitGitHubUrl } from '@/lib/hooks';
import type { HandsOnRequirement, HandsOnSubmission, PhaseProgressSchema } from '@/lib/api-client';
import type { TaskResult } from '@/lib/types';

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

function useCountdown(targetDate: string | null): string | null {
  const [timeLeft, setTimeLeft] = useState<string | null>(null);

  useEffect(() => {
    if (!targetDate) {
      setTimeLeft(null);
      return;
    }

    let interval: ReturnType<typeof setInterval> | null = null;

    const calculateTimeLeft = () => {
      const target = new Date(targetDate).getTime();
      const diff = target - Date.now();

      if (diff <= 0) {
        setTimeLeft(null);
        if (interval) {
          clearInterval(interval);
          interval = null;
        }
        return;
      }

      const minutes = Math.floor(diff / 60000);
      const seconds = Math.floor((diff % 60000) / 1000);
      setTimeLeft(`${minutes}m ${seconds}s`);
    };

    calculateTimeLeft();
    interval = setInterval(calculateTimeLeft, 1000);
    return () => {
      if (interval) clearInterval(interval);
    };
  }, [targetDate]);

  return timeLeft;
}

function CooldownTimer({ nextRetryAt }: { nextRetryAt: string }) {
  const timeLeft = useCountdown(nextRetryAt);

  if (!timeLeft) return null;

  return (
    <div className="mt-2 flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400">
      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
      <span>Next attempt available in {timeLeft}</span>
    </div>
  );
}

function TaskChecklist({ taskResults }: { taskResults: TaskResult[] }) {
  const [expandedTasks, setExpandedTasks] = useState<Set<string>>(() => new Set());
  const passedCount = taskResults.filter((t) => t.passed).length;
  const totalCount = taskResults.length;
  const allExpanded = taskResults.filter((t) => !t.passed).every((t) => expandedTasks.has(t.task_name));
  const failedTasks = taskResults.filter((t) => !t.passed);

  const toggleTask = useCallback((taskName: string) => {
    setExpandedTasks((prev) => {
      const next = new Set(prev);
      if (next.has(taskName)) {
        next.delete(taskName);
      } else {
        next.add(taskName);
      }
      return next;
    });
  }, []);

  const toggleAll = useCallback(() => {
    if (allExpanded) {
      setExpandedTasks(new Set());
    } else {
      setExpandedTasks(new Set(failedTasks.map((t) => t.task_name)));
    }
  }, [allExpanded, failedTasks]);

  return (
    <div className="mt-3">
      {/* Header row: summary + toggle */}
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <span className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">
            Task Checklist
          </span>
          <span className={`text-xs font-medium px-1.5 py-0.5 rounded-full ${
            passedCount === totalCount
              ? 'bg-emerald-100 dark:bg-emerald-900/40 text-emerald-700 dark:text-emerald-300'
              : 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300'
          }`}>
            {passedCount}/{totalCount}
          </span>
        </div>
        {failedTasks.length > 0 && (
          <button
            type="button"
            onClick={toggleAll}
            className="text-xs text-blue-600 dark:text-blue-400 hover:underline"
          >
            {allExpanded ? 'Collapse all' : 'Expand all'}
          </button>
        )}
      </div>

      {/* Scrollable task list */}
      <div className="max-h-52 overflow-y-auto rounded-lg border border-gray-200 dark:border-gray-700">
        <div className="divide-y divide-gray-200 dark:divide-gray-700">
          {taskResults.map((task) => {
            const isExpanded = expandedTasks.has(task.task_name);

            return (
              <div key={task.task_name} className="px-3 py-2">
                <button
                  type="button"
                  onClick={() => { if (!task.passed) toggleTask(task.task_name); }}
                  className={`flex items-center gap-2 w-full text-left ${task.passed ? 'cursor-default' : 'cursor-pointer'}`}
                  aria-expanded={task.passed ? undefined : isExpanded}
                >
                  {task.passed ? (
                    <svg className="w-4 h-4 text-emerald-500 shrink-0" fill="currentColor" viewBox="0 0 20 20">
                      <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                    </svg>
                  ) : (
                    <svg className="w-4 h-4 text-red-500 shrink-0" fill="currentColor" viewBox="0 0 20 20">
                      <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
                    </svg>
                  )}
                  <span className={`text-sm flex-1 ${task.passed ? 'text-gray-500 dark:text-gray-400 line-through' : 'text-gray-900 dark:text-white'}`}>
                    {task.task_name}
                  </span>
                  {!task.passed && (
                    <svg className={`w-3 h-3 text-gray-400 shrink-0 transition-transform ${isExpanded ? 'rotate-180' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
                    </svg>
                  )}
                </button>
                {!task.passed && isExpanded && (
                  <p className="mt-1.5 ml-6 text-xs text-gray-600 dark:text-gray-400 leading-relaxed">
                    {task.feedback}
                  </p>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
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
  const [validationMessages, setValidationMessages] = useState<Record<string, { message: string; isValid: boolean; taskResults?: TaskResult[] | null; nextRetryAt?: string | null }>>({});
  const submitMutation = useSubmitGitHubUrl();

  const getSubmissionForRequirement = (reqId: string) => {
    return submissions.find((s) => s.requirement_id === reqId);
  };

  const handleSubmit = async (requirementId: string) => {
    const url = urls[requirementId];
    if (!url) return;

    try {
      const result = await submitMutation.mutateAsync({ requirementId, url });
      setValidationMessages((prev) => ({
        ...prev,
        [requirementId]: {
          message: result.message,
          isValid: result.is_valid,
          taskResults: result.task_results,
          nextRetryAt: result.next_retry_at,
        },
      }));
      setUrls((prev) => ({ ...prev, [requirementId]: '' }));
    } catch (error: unknown) {
      // Extract lockout_until from 429 cooldown responses to show countdown timer
      let nextRetryAt: string | null = null;
      const apiError = error as { status?: number; detail?: { lockout_until?: string | null } };
      if (apiError.status === 429 && apiError.detail?.lockout_until) {
        nextRetryAt = apiError.detail.lockout_until;
      }

      setValidationMessages((prev) => ({
        ...prev,
        [requirementId]: {
          message: error instanceof Error ? error.message : 'Submission failed',
          isValid: false,
          nextRetryAt,
        },
      }));
    }
  };

  const stepsComplete = phaseProgress?.status === 'completed';

  return (
    <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-6">
      <div className="flex items-center gap-3 mb-6">
        <div className="text-3xl" aria-hidden="true">🎯</div>
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
          const isTokenType = req.submission_type === 'ctf_token' || req.submission_type === 'networking_token';
          const isJsonResponse = req.submission_type === 'journal_api_response';
          const isGitHubUrlType =
            req.submission_type === 'github_profile'
            || req.submission_type === 'profile_readme'
            || req.submission_type === 'repo_fork'
            || req.submission_type === 'code_analysis';

          // Parse persisted feedback from submission if no fresh validation message
          const persistedTaskResults = submission?.feedback_json
            ? (JSON.parse(submission.feedback_json) as TaskResult[])
            : null;
          const taskResults = validationMsg?.taskResults ?? persistedTaskResults;

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
                  {req.note && (
                    <p className="mt-1 text-xs text-gray-500 dark:text-gray-500 italic">
                      {req.note}
                    </p>
                  )}
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

              {validationMsg && (
                <div
                  id={`msg-${req.id}`}
                  role="status"
                  className={`mt-3 p-3 rounded-lg text-sm ${
                    validationMsg.isValid
                      ? 'bg-emerald-100 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-300'
                      : 'bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-300'
                  }`}
                >
                  {validationMsg.message}
                </div>
              )}

              {/* Countdown timer for next retry - only on failed validations */}
              {validationMsg?.nextRetryAt && !validationMsg.isValid && (
                <CooldownTimer nextRetryAt={validationMsg.nextRetryAt} />
              )}

              {/* Task Results for CODE_ANALYSIS submissions (fresh or persisted) */}
              {taskResults && taskResults.length > 0 && (
                <TaskChecklist taskResults={taskResults} />
              )}

              {!isPassed && githubUsername && (
                <div className="mt-4">
                  {submission?.submitted_value && (
                    <div className="mb-2 text-sm">
                      <span className="text-gray-500 dark:text-gray-400">Submitted: </span>
                      {isTokenType || isJsonResponse ? (
                        <span
                          className="text-gray-700 dark:text-gray-300 font-mono text-xs break-all"
                          title={submission.submitted_value}
                        >
                          {submission.submitted_value.length > 60
                            ? `${submission.submitted_value.slice(0, 60)}...`
                            : submission.submitted_value}
                        </span>
                      ) : (
                        <a
                          href={submission.submitted_value}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-blue-600 dark:text-blue-400 hover:underline break-all"
                        >
                          {submission.submitted_value}
                        </a>
                      )}
                    </div>
                  )}

                  <div className="flex gap-2">
                    <label htmlFor={`url-${req.id}`} className="sr-only">
                      {isTokenType
                        ? `Completion token for ${req.name}`
                        : isJsonResponse
                          ? `JSON response for ${req.name}`
                          : isGitHubUrlType
                            ? `GitHub URL for ${req.name}`
                            : `Evidence URL for ${req.name}`}
                    </label>
                    {isJsonResponse ? (
                      <textarea
                        id={`url-${req.id}`}
                        rows={4}
                        value={urls[req.id] || ''}
                        onChange={(e) => {
                          setUrls((prev) => ({ ...prev, [req.id]: e.target.value }));
                          if (validationMessages[req.id]) {
                            setValidationMessages((prev) => {
                              const { [req.id]: _, ...rest } = prev;
                              return rest;
                            });
                          }
                        }}
                        placeholder="Paste your JSON response from GET /entries"
                        className="flex-1 px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                        disabled={submitMutation.isPending}
                        aria-describedby={validationMsg ? `msg-${req.id}` : undefined}
                      />
                    ) : (
                      <input
                        id={`url-${req.id}`}
                        type={isTokenType ? 'text' : 'url'}
                        value={urls[req.id] || ''}
                        onChange={(e) => {
                          setUrls((prev) => ({ ...prev, [req.id]: e.target.value }));
                          if (validationMessages[req.id]) {
                            setValidationMessages((prev) => {
                              const { [req.id]: _, ...rest } = prev;
                              return rest;
                            });
                          }
                        }}
                        placeholder={
                          isTokenType
                            ? 'Paste your completion token here'
                            : isGitHubUrlType
                              ? 'https://github.com/username/repo'
                              : 'https://example.com/evidence'
                        }
                        className="flex-1 px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                        disabled={submitMutation.isPending}
                        aria-describedby={validationMsg ? `msg-${req.id}` : undefined}
                      />
                    )}
                    <button
                      onClick={() => handleSubmit(req.id)}
                      disabled={!urls[req.id] || submitMutation.isPending}
                      className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                    >
                      {submitMutation.isPending ? (
                        <span className="flex items-center gap-2">
                          <svg className="animate-spin w-4 h-4" viewBox="0 0 24 24">
                            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                          </svg>
                          Submitting...
                        </span>
                      ) : 'Submit'}
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
            <span role="img" aria-label="Celebration">🎉</span> All verifications complete! Phase {phaseNumber} finished!
          </p>
          <a
            href={`/${nextPhaseSlug}`}
            className="inline-flex items-center px-4 py-2 bg-emerald-600 text-white rounded-lg font-medium hover:bg-emerald-700 transition-colors"
          >
            Continue to Phase {phaseNumber + 1} →
          </a>
        </div>
      )}

      {allHandsOnValidated && !stepsComplete && (
        <div className="mt-6 p-4 bg-amber-50 dark:bg-amber-900/20 rounded-lg border border-amber-200 dark:border-amber-800 text-center">
          <p className="text-amber-700 dark:text-amber-300 font-medium">
            <span role="img" aria-label="Verified">✅</span> All hands-on requirements verified! Complete all learning steps to finish Phase {phaseNumber}.
          </p>
        </div>
      )}
    </div>
  );
}
