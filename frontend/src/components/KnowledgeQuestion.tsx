import { useState, useCallback, useId } from 'react';
import type { QuestionSchema } from '@/lib/api-client';
import { LockoutError } from '@/lib/api-client';
import { useApi } from '@/lib/hooks';
import { QUESTION_ANSWER_MAX_CHARS, QUESTION_ANSWER_MIN_CHARS } from '@/lib/constants';

interface KnowledgeQuestionProps {
  question: QuestionSchema;
  topicId: string;
  isAnswered: boolean;
  initialLockoutUntil?: Date | null;
  initialAttemptsUsed?: number;
  onSubmit: (answer: string, scenarioContext?: string) => Promise<{ is_passed: boolean; llm_feedback?: string | null; attempts_used?: number | null; lockout_until?: string | null }>;
}

export function KnowledgeQuestion({
  question,
  topicId,
  isAnswered: initialIsAnswered,
  initialLockoutUntil = null,
  initialAttemptsUsed = 0,
  onSubmit,
}: KnowledgeQuestionProps) {
  const [answer, setAnswer] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isPassed, setIsPassed] = useState(initialIsAnswered);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [lockoutUntil, setLockoutUntil] = useState<Date | null>(initialLockoutUntil);
  const [attemptsUsed, setAttemptsUsed] = useState(initialAttemptsUsed);

  // Scenario state - user must explicitly start the question
  const [isStarted, setIsStarted] = useState(false);
  const [scenarioPrompt, setScenarioPrompt] = useState<string | null>(null);
  const [isLoadingScenario, setIsLoadingScenario] = useState(false);
  const [scenarioError, setScenarioError] = useState<string | null>(null);

  // API client hook
  const api = useApi();

  const id = useId();
  const promptId = `${id}-prompt`;
  const textareaId = `${id}-textarea`;
  const errorId = `${id}-error`;
  const feedbackId = `${id}-feedback`;
  const charCountId = `${id}-charcount`;
  const lockoutId = `${id}-lockout`;

  // Fetch scenario when user clicks "Start"
  const handleStartQuestion = useCallback(async () => {
    setIsStarted(true);
    setIsLoadingScenario(true);
    setScenarioError(null);
    try {
      const result = await api.getScenarioQuestion(topicId, question.id);
      setScenarioPrompt(result.scenario_prompt);
    } catch (err) {
      console.error('Failed to fetch scenario:', err);
      if (err instanceof LockoutError) {
        if (err.lockoutUntil) {
          setLockoutUntil(new Date(err.lockoutUntil));
        }
        setAttemptsUsed(err.attemptsUsed);
      } else {
        // Show error - no fallback to base question
        setScenarioError('Scenario generation is temporarily unavailable. Please try again in a few minutes.');
        setIsStarted(false); // Allow retry
      }
    } finally {
      setIsLoadingScenario(false);
    }
  }, [api, topicId, question.id]);

  // Display prompt: only show scenario if we have one (no fallback)
  const displayPrompt = scenarioPrompt;

  const formatLockoutTime = (until: Date): string => {
    const now = new Date();
    const diffMs = until.getTime() - now.getTime();
    const diffMins = Math.ceil(diffMs / 60000);
    if (diffMins <= 0) return 'less than a minute'; // Expired or about to expire
    if (diffMins === 1) return 'less than a minute';
    if (diffMins < 60) return `${diffMins} minutes`;
    const hours = Math.floor(diffMins / 60);
    const mins = diffMins % 60;
    return mins > 0 ? `${hours}h ${mins}m` : `${hours} hour${hours > 1 ? 's' : ''}`;
  };

  const isLockedOut = lockoutUntil !== null && lockoutUntil > new Date();

  const handleSubmit = useCallback(async () => {
    if (answer.length < QUESTION_ANSWER_MIN_CHARS) {
      setError(`Answer must be at least ${QUESTION_ANSWER_MIN_CHARS} characters.`);
      return;
    }

    setIsSubmitting(true);
    setError(null);
    setFeedback(null);

    try {
      // Always pass the scenario prompt - we no longer have fallback
      const result = await onSubmit(answer, scenarioPrompt || undefined);

      if (result.is_passed) {
        setIsPassed(true);
        setLockoutUntil(null); // Clear any lockout on success
        setAttemptsUsed(0); // Reset attempts on success
        setFeedback(result.llm_feedback || "Correct. You demonstrated solid understanding of the key concepts.");
      } else {
        if (result.attempts_used != null) {
          setAttemptsUsed(result.attempts_used);
        }
        // Handle lockout_until from response (set when user reaches max attempts)
        if (result.lockout_until) {
          setLockoutUntil(new Date(result.lockout_until));
          setFeedback(null); // Clear feedback when locked out
        } else {
          setFeedback(result.llm_feedback || "Your answer needs more detail. Address the core concepts and try again.");
        }
      }
    } catch (err) {
      console.error('Failed to submit answer:', err);
      if (err instanceof LockoutError) {
        if (err.lockoutUntil) {
          setLockoutUntil(new Date(err.lockoutUntil));
        }
        setAttemptsUsed(err.attemptsUsed);
        setFeedback(null);
      } else {
        setError('Failed to submit your answer. Please try again.');
      }
    } finally {
      setIsSubmitting(false);
    }
  }, [answer, onSubmit, scenarioPrompt]);

  const charCount = answer.length;
  const isOverLimit = charCount > QUESTION_ANSWER_MAX_CHARS;
  const canSubmit = charCount >= QUESTION_ANSWER_MIN_CHARS && !isOverLimit && !isSubmitting && !isPassed && !isLockedOut && !isLoadingScenario && isStarted && scenarioPrompt;

  // Not started yet - show compact row with start button (or error with retry)
  if (!isStarted && !isPassed && !isLockedOut) {
    return (
      <div className="border rounded-lg p-4 bg-white dark:bg-gray-800 border-gray-200 dark:border-gray-700">
        <div className="flex items-center gap-3">
          <div className={`flex-shrink-0 w-6 h-6 rounded-full flex items-center justify-center ${
            scenarioError
              ? 'bg-amber-100 dark:bg-amber-900/30 text-amber-600 dark:text-amber-400'
              : 'bg-gray-200 dark:bg-gray-600 text-gray-600 dark:text-gray-300'
          }`}>
            {scenarioError ? (
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
              </svg>
            ) : (
              <span className="text-xs font-medium">?</span>
            )}
          </div>
          <div className="flex-1">
            {scenarioError ? (
              <p className="text-amber-700 dark:text-amber-400 text-sm">
                {scenarioError}
              </p>
            ) : (
              <p className="text-gray-600 dark:text-gray-400 text-sm">
                Ready to test your knowledge? A unique scenario will be generated for you.
              </p>
            )}
          </div>
          <button
            type="button"
            onClick={handleStartQuestion}
            disabled={isLoadingScenario}
            className={`px-4 py-2 rounded-lg font-medium text-sm transition-colors whitespace-nowrap ${
              isLoadingScenario
                ? 'bg-gray-400 cursor-not-allowed text-white'
                : 'bg-blue-600 hover:bg-blue-700 text-white'
            }`}
          >
            {isLoadingScenario ? 'Loading...' : scenarioError ? 'Try Again' : 'Start Knowledge Check'}
          </button>
        </div>
      </div>
    );
  }

  // Already passed - show simple completion state (no question text)
  if (isPassed && !isStarted) {
    return (
      <div className="border rounded-lg p-4 bg-green-50 dark:bg-green-900/20 border-green-200 dark:border-green-800">
        <div className="flex items-center gap-3">
          <div className="flex-shrink-0 w-6 h-6 rounded-full flex items-center justify-center bg-green-500 text-white">
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
            </svg>
          </div>
          <p className="text-green-700 dark:text-green-300 text-sm font-medium">
            ✓ You've passed this question
          </p>
        </div>
      </div>
    );
  }

  // Locked out before starting - show lockout message (no question text)
  if (isLockedOut && !isStarted) {
    return (
      <div className="border rounded-lg p-4 bg-white dark:bg-gray-800 border-gray-200 dark:border-gray-700">
        <div className="flex items-center gap-3">
          <div className="flex-shrink-0 w-6 h-6 rounded-full flex items-center justify-center bg-gray-200 dark:bg-gray-600 text-gray-500 dark:text-gray-400">
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          </div>
          <div className="flex-1">
            <p className="text-gray-700 dark:text-gray-300 text-sm font-medium">
              Available in {formatLockoutTime(lockoutUntil!)}
            </p>
            <p className="text-gray-500 dark:text-gray-400 text-xs mt-0.5">
              Review the learning material above before trying again.
            </p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className={`border rounded-lg p-4 ${
      isPassed
        ? 'bg-green-50 dark:bg-green-900/20 border-green-200 dark:border-green-800'
        : 'bg-white dark:bg-gray-800 border-gray-200 dark:border-gray-700'
    }`}>
      <div className="flex items-start gap-3 mb-3">
        <div className={`flex-shrink-0 w-6 h-6 rounded-full flex items-center justify-center ${
          isPassed
            ? 'bg-green-500 text-white'
            : 'bg-gray-200 dark:bg-gray-600 text-gray-600 dark:text-gray-300'
        }`}>
          {isPassed ? (
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
            </svg>
          ) : (
            <span className="text-xs font-medium">?</span>
          )}
        </div>
        <div className="flex-1">
          {isLoadingScenario ? (
            <div className="animate-pulse">
              <div className="h-4 bg-gray-200 dark:bg-gray-700 rounded w-3/4 mb-2"></div>
              <div className="h-4 bg-gray-200 dark:bg-gray-700 rounded w-1/2"></div>
            </div>
          ) : (
            <p id={promptId} className="text-gray-900 dark:text-white font-medium">{displayPrompt}</p>
          )}
          {scenarioError && (
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-1 italic">{scenarioError}</p>
          )}
        </div>
      </div>

      {isPassed ? (
        <div className="ml-9">
          <p className="text-green-700 dark:text-green-300 text-sm">
            ✓ You've passed this question
          </p>
          {feedback && (
            <p id={feedbackId} className="text-gray-600 dark:text-gray-400 text-sm mt-2 italic">
              {feedback}
            </p>
          )}
        </div>
      ) : (
        <div className="ml-9 space-y-3">
          <div className="relative">
            <textarea
              id={textareaId}
              value={answer}
              onChange={(e) => {
                setAnswer(e.target.value);
                setError(null);
              }}
              placeholder="Answer concisely as you would in an interview (1-2 sentences)..."
              rows={4}
              maxLength={QUESTION_ANSWER_MAX_CHARS + 100}
              disabled={isSubmitting || isLockedOut || isLoadingScenario}
              aria-labelledby={promptId}
              aria-describedby={[error ? errorId : null, feedback && !isPassed ? feedbackId : null, isLockedOut ? lockoutId : null, charCountId].filter(Boolean).join(' ') || undefined}
              aria-invalid={!!error || isOverLimit}
              className={`w-full px-3 py-2 border rounded-lg resize-none focus:outline-none focus:ring-2
                ${isOverLimit
                  ? 'border-red-300 focus:ring-red-500'
                  : 'border-gray-300 dark:border-gray-600 focus:ring-blue-500'
                }
                bg-white dark:bg-gray-700 text-gray-900 dark:text-white
                placeholder-gray-400 dark:placeholder-gray-500
                disabled:opacity-50 disabled:cursor-not-allowed`}
            />
            <div
              id={charCountId}
              className={`absolute bottom-2 right-2 text-xs ${
                isOverLimit ? 'text-red-500' : 'text-gray-400'
              }`}
              aria-live="polite"
              aria-atomic="true"
            >
              <span className="sr-only">{charCount} of {QUESTION_ANSWER_MAX_CHARS} characters</span>
              <span aria-hidden="true">{charCount}/{QUESTION_ANSWER_MAX_CHARS}</span>
            </div>
          </div>

          {error && (
            <p id={errorId} className="text-red-600 dark:text-red-400 text-sm" role="alert">{error}</p>
          )}

          {isLockedOut && lockoutUntil && (
            <div
              id={lockoutId}
              className="flex items-start gap-3 p-3 bg-gray-50 dark:bg-gray-900/50 border border-gray-200 dark:border-gray-700 rounded-lg"
              role="alert"
            >
              <div className="flex-shrink-0 w-8 h-8 bg-gray-200 dark:bg-gray-700 rounded-full flex items-center justify-center">
                <svg className="w-4 h-4 text-gray-500 dark:text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-gray-900 dark:text-gray-100">
                  Available in {formatLockoutTime(lockoutUntil)}
                </p>
                <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                  Review the learning material above before trying again.
                </p>
              </div>
            </div>
          )}

          {feedback && !isPassed && (
            <div
              id={feedbackId}
              className="p-3 bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800 rounded-lg"
              aria-live="polite"
            >
              <p className="text-yellow-800 dark:text-yellow-200 text-sm">
                <strong>Feedback:</strong> {feedback}
              </p>
              {attemptsUsed > 0 && attemptsUsed < 3 && (
                <p className="text-yellow-700 dark:text-yellow-300 text-xs mt-2">
                  {attemptsUsed}/3 attempts used
                </p>
              )}
            </div>
          )}

          <button
            type="button"
            onClick={handleSubmit}
            disabled={!canSubmit}
            className={`px-4 py-2 rounded-lg font-medium text-sm transition-colors ${
              canSubmit
                ? 'bg-blue-600 hover:bg-blue-700 text-white'
                : 'bg-gray-200 dark:bg-gray-700 text-gray-500 dark:text-gray-400 cursor-not-allowed'
            }`}
          >
            {isSubmitting ? (
              <span className="flex items-center gap-2">
                <svg className="animate-spin w-4 h-4" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
                Checking...
              </span>
            ) : (
              'Submit Answer'
            )}
          </button>
        </div>
      )}
    </div>
  );
}
