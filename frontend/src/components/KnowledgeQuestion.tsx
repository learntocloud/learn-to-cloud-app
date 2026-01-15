/**
 * KnowledgeQuestion component for answering topic questions.
 */

import { useState } from 'react';
import type { QuestionSchema } from '@/lib/api-client';

interface KnowledgeQuestionProps {
  question: QuestionSchema;
  isAnswered: boolean;
  onSubmit: (answer: string) => Promise<{ is_passed: boolean; llm_feedback?: string | null }>;
}

const MAX_CHARS = 2000;
const MIN_CHARS = 10;

export function KnowledgeQuestion({
  question,
  isAnswered: initialIsAnswered,
  onSubmit,
}: KnowledgeQuestionProps) {
  const [answer, setAnswer] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isPassed, setIsPassed] = useState(initialIsAnswered);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async () => {
    if (answer.length < MIN_CHARS) {
      setError(`Answer must be at least ${MIN_CHARS} characters.`);
      return;
    }

    setIsSubmitting(true);
    setError(null);
    setFeedback(null);

    try {
      const result = await onSubmit(answer);
      
      if (result.is_passed) {
        setIsPassed(true);
        setFeedback(result.llm_feedback || "Great job! You've demonstrated understanding of this concept.");
      } else {
        setFeedback(result.llm_feedback || "Not quite. Review the material and try again.");
      }
    } catch (err) {
      console.error('Failed to submit answer:', err);
      setError('Failed to submit your answer. Please try again.');
    } finally {
      setIsSubmitting(false);
    }
  };

  const charCount = answer.length;
  const isOverLimit = charCount > MAX_CHARS;
  const canSubmit = charCount >= MIN_CHARS && !isOverLimit && !isSubmitting && !isPassed;

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
        <p className="text-gray-900 dark:text-white font-medium">{question.prompt}</p>
      </div>

      {isPassed ? (
        <div className="ml-9">
          <p className="text-green-700 dark:text-green-300 text-sm">
            ✓ You've passed this question
          </p>
          {feedback && (
            <p className="text-gray-600 dark:text-gray-400 text-sm mt-2 italic">
              {feedback}
            </p>
          )}
        </div>
      ) : (
        <div className="ml-9 space-y-3">
          <div className="relative">
            <textarea
              value={answer}
              onChange={(e) => {
                setAnswer(e.target.value);
                setError(null);
              }}
              placeholder="Type your answer here..."
              rows={4}
              maxLength={MAX_CHARS + 100}
              disabled={isSubmitting}
              className={`w-full px-3 py-2 border rounded-lg resize-none focus:outline-none focus:ring-2 
                ${isOverLimit 
                  ? 'border-red-300 focus:ring-red-500' 
                  : 'border-gray-300 dark:border-gray-600 focus:ring-blue-500'
                }
                bg-white dark:bg-gray-700 text-gray-900 dark:text-white
                placeholder-gray-400 dark:placeholder-gray-500
                disabled:opacity-50 disabled:cursor-not-allowed`}
            />
            <div className={`absolute bottom-2 right-2 text-xs ${
              isOverLimit ? 'text-red-500' : 'text-gray-400'
            }`}>
              {charCount}/{MAX_CHARS}
            </div>
          </div>

          {error && (
            <p className="text-red-600 dark:text-red-400 text-sm">{error}</p>
          )}

          {feedback && !isPassed && (
            <div className="p-3 bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800 rounded-lg">
              <p className="text-yellow-800 dark:text-yellow-200 text-sm">
                <strong>Feedback:</strong> {feedback}
              </p>
            </div>
          )}

          <button
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
