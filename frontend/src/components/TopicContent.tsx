/**
 * TopicContent component for displaying learning steps and questions.
 * Uses the topic ID (e.g., "phase0-topic1") for API calls.
 */

import { useState } from 'react';
import type { TopicDetailSchema, ProviderOptionSchema } from '@/lib/api-client';
import { useCompleteStep, useUncompleteStep, useSubmitQuestionAnswer } from '@/lib/hooks';
import { KnowledgeQuestion } from './KnowledgeQuestion';

function ProviderOptions({ options }: { options: ProviderOptionSchema[] }) {
  const [selectedProvider, setSelectedProvider] = useState<string>(options[0]?.provider || "aws");

  const selectedOption = options.find(o => o.provider === selectedProvider);

  const providerLabels: Record<string, { name: string }> = {
    aws: { name: "AWS" },
    azure: { name: "Azure" },
    gcp: { name: "GCP" },
  };

  return (
    <div className="mt-3 border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden">
      <div role="tablist" className="flex border-b border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800/50">
        {options.map((option) => {
          const provider = providerLabels[option.provider] || { name: option.provider };
          const isSelected = selectedProvider === option.provider;

          return (
            <button
              key={option.provider}
              onClick={() => setSelectedProvider(option.provider)}
              role="tab"
              aria-selected={isSelected}
              aria-controls={`tabpanel-${option.provider}`}
              className={`flex-1 px-4 py-2 text-sm font-medium transition-colors ${
                isSelected
                  ? "bg-white dark:bg-gray-800 text-gray-900 dark:text-white border-b-2 border-blue-500 -mb-px"
                  : "text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white hover:bg-gray-100 dark:hover:bg-gray-700/50"
              }`}
            >
              {provider.name}
            </button>
          );
        })}
      </div>

      {selectedOption && (
        <div
          role="tabpanel"
          id={`tabpanel-${selectedOption.provider}`}
          className="p-4 bg-white dark:bg-gray-800"
        >
          <a
            href={selectedOption.url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-blue-600 hover:text-blue-800 dark:text-blue-400 dark:hover:text-blue-300 hover:underline font-medium"
          >
            {selectedOption.title}
            <svg className="w-4 h-4 inline-block ml-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
            </svg>
          </a>
          {selectedOption.description && (
            <p className="mt-2 text-sm text-gray-600 dark:text-gray-400">
              {selectedOption.description}
            </p>
          )}
        </div>
      )}
    </div>
  );
}

interface TopicContentProps {
  topic: TopicDetailSchema;
  isAuthenticated: boolean;
}

export function TopicContent({
  topic,
  isAuthenticated,
}: TopicContentProps) {
  const completeStepMutation = useCompleteStep();
  const uncompleteStepMutation = useUncompleteStep();
  const submitQuestionMutation = useSubmitQuestionAnswer();

  // Parent uses key={topic.id} to reset state when topic changes
  const [completedSteps, setCompletedSteps] = useState<number[]>(topic.completed_step_orders || []);
  const [passedQuestions, setPassedQuestions] = useState<string[]>(topic.passed_question_ids || []);
  const [togglingStep, setTogglingStep] = useState<number | null>(null);
  const [copiedStep, setCopiedStep] = useState<number | null>(null);

  const handleStepToggle = async (stepOrder: number) => {
    if (!isAuthenticated) return;

    const isCurrentlyCompleted = completedSteps.includes(stepOrder);

    setTogglingStep(stepOrder);
    try {
      let response;
      if (isCurrentlyCompleted) {
        // Uncomplete the step (and any steps after it)
        response = await uncompleteStepMutation.mutateAsync({
          topicId: topic.id,
          stepOrder,
        });
      } else {
        response = await completeStepMutation.mutateAsync({
          topicId: topic.id,
          stepOrder,
        });
      }
      setCompletedSteps(response.completed_steps);
    } catch (err) {
      console.error("Failed to toggle step:", err);
    } finally {
      setTogglingStep(null);
    }
  };

  const handleQuestionAnswer = async (questionId: string, answer: string, scenarioContext?: string) => {
    if (!isAuthenticated) return { is_passed: false, llm_feedback: 'Not authenticated' };

    // Don't catch errors here - let them propagate to KnowledgeQuestion
    // so it can handle LockoutError and show the lockout UI
    const result = await submitQuestionMutation.mutateAsync({
      topicId: topic.id,
      questionId,
      answer,
      scenarioContext,
    });

    // Update local state if passed (for immediate UI feedback)
    if (result.is_passed) {
      setPassedQuestions((prev) => (prev.includes(questionId) ? prev : [...prev, questionId]));
    }

    return result;
  };

  const isStepCompleted = (order: number) => completedSteps.includes(order);
  const isQuestionPassed = (questionId: string) => passedQuestions.includes(questionId);

  const getQuestionLockout = (questionId: string): Date | null => {
    const lockout = topic.locked_questions?.find((l) => l.question_id === questionId);
    if (!lockout) return null;
    const until = new Date(lockout.lockout_until);
    // Only return if lockout is still active
    return until > new Date() ? until : null;
  };

  const getQuestionAttemptsUsed = (questionId: string): number => {
    const lockout = topic.locked_questions?.find((l) => l.question_id === questionId);
    return lockout?.attempts_used ?? 0;
  };

  const handleCopyCode = async (stepOrder: number, code: string) => {
    try {
      await navigator.clipboard.writeText(code);
      setCopiedStep(stepOrder);
      window.setTimeout(() => {
        setCopiedStep((current) => (current === stepOrder ? null : current));
      }, 1200);
    } catch (err) {
      console.error('Failed to copy to clipboard:', err);
    }
  };

  return (
    <div className="space-y-6">
      {topic.learning_steps && topic.learning_steps.length > 0 && (
        <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 overflow-hidden">
          <div className="p-4 border-b border-gray-200 dark:border-gray-700">
            <h3 className="font-semibold text-gray-900 dark:text-white flex items-center gap-2">
              📚 Learning Steps
              <span className="text-sm font-normal text-gray-500 dark:text-gray-400">
                ({completedSteps.length}/{topic.learning_steps.length})
              </span>
            </h3>
          </div>

          <div className="divide-y divide-gray-200 dark:divide-gray-700">
            {topic.learning_steps.map((step) => {
              const completed = isStepCompleted(step.order);
              const isToggling = togglingStep === step.order;

              return (
                <div
                  key={step.order}
                  className={`p-4 transition-colors ${
                    completed
                      ? 'bg-emerald-50/50 dark:bg-emerald-900/10'
                      : ''
                  }`}
                >
                  <div className="flex items-start gap-3">
                    {isAuthenticated && (
                      <button
                        onClick={() => handleStepToggle(step.order)}
                        disabled={isToggling}
                        role="checkbox"
                        aria-checked={completed}
                        aria-label={`Mark step ${step.order} as ${completed ? 'incomplete' : 'complete'}`}
                        className={`mt-1 w-5 h-5 rounded border-2 flex items-center justify-center transition-all ${
                          completed
                            ? 'bg-emerald-500 border-emerald-500 text-white'
                            : 'border-gray-300 dark:border-gray-600 hover:border-emerald-400'
                        } ${isToggling ? 'opacity-50' : ''}`}
                      >
                        {completed && (
                          <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                            <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                          </svg>
                        )}
                      </button>
                    )}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-start gap-2">
                        <span className="font-medium text-gray-500 dark:text-gray-400 text-sm">
                          {step.order}.
                        </span>
                        <div className="flex-1">
                          <p className={`${completed ? 'text-gray-500 dark:text-gray-400' : 'text-gray-900 dark:text-white'}`}>
                            {step.action && (
                              <strong className="font-semibold">{step.action} </strong>
                            )}
                            {step.url ? (
                              <a
                                href={step.url}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="text-blue-600 dark:text-blue-400 hover:underline"
                              >
                                {step.title || step.text}
                              </a>
                            ) : (
                              <span>{step.title || step.text}</span>
                            )}
                          </p>
                          {step.description && (
                            <p className="mt-1 text-sm text-gray-600 dark:text-gray-400">
                              {step.description}
                            </p>
                          )}


                          {step.code && (
                            <div className="mt-3 relative">
                              <pre className="bg-gray-900 dark:bg-gray-950 text-gray-100 text-sm p-4 rounded-lg overflow-x-auto">
                                <code>{step.code}</code>
                              </pre>
                              <button
                                onClick={() => handleCopyCode(step.order, step.code!)}
                                className="absolute top-2 right-2 p-1.5 text-gray-400 hover:text-white bg-gray-800 hover:bg-gray-700 rounded transition-colors"
                                title={copiedStep === step.order ? 'Copied' : 'Copy to clipboard'}
                                aria-label={copiedStep === step.order ? 'Copied to clipboard' : 'Copy code to clipboard'}
                              >
                                {copiedStep === step.order ? (
                                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                                  </svg>
                                ) : (
                                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
                                  </svg>
                                )}
                              </button>
                            </div>
                          )}

                          {step.options && step.options.length > 0 && (
                            <ProviderOptions options={step.options} />
                          )}
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {topic.questions && topic.questions.length > 0 && (
        <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 overflow-hidden">
          <div className="p-4 border-b border-gray-200 dark:border-gray-700">
            <h3 className="font-semibold text-gray-900 dark:text-white flex items-center gap-2">
              ❓ Knowledge Check
              <span className="text-sm font-normal text-gray-500 dark:text-gray-400">
                ({passedQuestions.length}/{topic.questions.length})
              </span>
            </h3>
          </div>

          <div className="p-4 space-y-4">
            {!isAuthenticated ? (
              <p className="text-sm text-gray-500 dark:text-gray-400 italic">
                Sign in to answer knowledge questions and track your progress.
              </p>
            ) : (
              topic.questions.map((question) => (
                <KnowledgeQuestion
                  key={question.id}
                  question={question}
                  topicId={topic.id}
                  isAnswered={isQuestionPassed(question.id)}
                  initialLockoutUntil={getQuestionLockout(question.id)}
                  initialAttemptsUsed={getQuestionAttemptsUsed(question.id)}
                  onSubmit={(answer, scenarioContext) => handleQuestionAnswer(question.id, answer, scenarioContext)}
                />
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
}
