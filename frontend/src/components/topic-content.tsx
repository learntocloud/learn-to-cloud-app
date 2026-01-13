"use client";

import { useState, useEffect } from "react";
import type { Topic, TopicWithProgress, TopicQuestionsStatus, TopicStepProgress } from "@/lib/types";
import { useApi } from "@/lib/use-api";
import { KnowledgeQuestion } from "./knowledge-question";
import { ProviderOptions } from "./provider-options";

// Helper to render description text with proper formatting for bullet points
function FormattedDescription({ text }: { text: string }) {
  // Check if text contains bullet points (• or lines starting with -)
  const hasBullets = text.includes('•') || /\n\s*-\s/.test(text);
  
  if (hasBullets) {
    // Split by newlines and render each line
    const lines = text.split('\n');
    return (
      <div className="space-y-1">
        {lines.map((line, i) => {
          const trimmed = line.trim();
          if (!trimmed) return null;
          
          // Check if line starts with bullet
          const isBullet = trimmed.startsWith('•') || trimmed.startsWith('-');
          
          if (isBullet) {
            // Remove the bullet character and render as list item
            const content = trimmed.replace(/^[•\-]\s*/, '');
            return (
              <div key={i} className="flex items-start gap-2 ml-2">
                <span className="text-blue-500 dark:text-blue-400 mt-0.5">•</span>
                <span>{content}</span>
              </div>
            );
          }
          
          // Regular paragraph line
          return <p key={i}>{trimmed}</p>;
        })}
      </div>
    );
  }
  
  // No bullets - check if has newlines for numbered lists or paragraphs
  if (text.includes('\n')) {
    return (
      <div className="space-y-2">
        {text.split('\n').filter(line => line.trim()).map((line, i) => (
          <p key={i}>{line.trim()}</p>
        ))}
      </div>
    );
  }
  
  // Simple text
  return <span>{text}</span>;
}

interface TopicContentProps {
  topic: Topic | TopicWithProgress;
  isAuthenticated: boolean;
  onStepProgressChange?: (completedCount: number) => void;
  onQuestionProgressChange?: (completedCount: number) => void;
}

export function TopicContent({ 
  topic, 
  isAuthenticated,
  onStepProgressChange,
  onQuestionProgressChange,
}: TopicContentProps) {
  const api = useApi();
  
  // State for step progress
  const [stepProgress, setStepProgress] = useState<TopicStepProgress | null>(null);
  const [loadingSteps, setLoadingSteps] = useState(false);
  const [togglingStep, setTogglingStep] = useState<number | null>(null);
  
  // State for knowledge questions
  const [questionsStatus, setQuestionsStatus] = useState<TopicQuestionsStatus | null>(null);
  const [loadingQuestions, setLoadingQuestions] = useState(false);

  // Fetch step progress for authenticated users
  useEffect(() => {
    if (isAuthenticated && topic.learning_steps.length > 0) {
      setLoadingSteps(true);
      api.getTopicStepProgress(topic.id, topic.learning_steps.length)
        .then((progress) => {
          setStepProgress(progress);
          onStepProgressChange?.(progress.completed_steps.length);
        })
        .catch((err) => {
          console.error("Failed to fetch step progress:", err);
          // Set default progress on error
          setStepProgress({
            topic_id: topic.id,
            completed_steps: [],
            total_steps: topic.learning_steps.length,
            next_unlocked_step: 1,
          });
          onStepProgressChange?.(0);
        })
        .finally(() => {
          setLoadingSteps(false);
        });
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isAuthenticated, topic.id, topic.learning_steps.length]);

  // Fetch question status for authenticated users
  useEffect(() => {
    if (isAuthenticated && topic.questions && topic.questions.length > 0) {
      setLoadingQuestions(true);
      api.getTopicQuestionsStatus(topic.id)
        .then((status) => {
          setQuestionsStatus(status);
          onQuestionProgressChange?.(status.passed_questions);
        })
        .catch((err) => {
          console.error("Failed to fetch question status:", err);
        })
        .finally(() => {
          setLoadingQuestions(false);
        });
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isAuthenticated, topic.id, topic.questions?.length]);

  const handleQuestionPass = () => {
    // Refresh question status when a question is passed
    if (topic.questions && topic.questions.length > 0) {
      api.getTopicQuestionsStatus(topic.id)
        .then((status) => {
          setQuestionsStatus(status);
          onQuestionProgressChange?.(status.passed_questions);
        })
        .catch((err) => {
          console.error("Failed to refresh question status:", err);
        });
    }
  };

  const handleStepToggle = async (stepOrder: number) => {
    if (!isAuthenticated || !stepProgress) return;
    
    const isCompleted = stepProgress.completed_steps.includes(stepOrder);
    setTogglingStep(stepOrder);
    
    try {
      if (isCompleted) {
        // Uncomplete this step (and all after it)
        await api.uncompleteStep(topic.id, stepOrder);
        // Update local state
        const newCompleted = stepProgress.completed_steps.filter(s => s < stepOrder);
        setStepProgress({
          ...stepProgress,
          completed_steps: newCompleted,
          next_unlocked_step: stepOrder,
        });
        onStepProgressChange?.(newCompleted.length);
      } else {
        // Complete this step
        await api.completeStep(topic.id, stepOrder);
        // Update local state
        const newCompleted = [...stepProgress.completed_steps, stepOrder].sort((a, b) => a - b);
        setStepProgress({
          ...stepProgress,
          completed_steps: newCompleted,
          next_unlocked_step: Math.min(stepOrder + 1, topic.learning_steps.length),
        });
        onStepProgressChange?.(newCompleted.length);
      }
    } catch (err) {
      console.error("Failed to toggle step:", err);
    } finally {
      setTogglingStep(null);
    }
  };

  // Helper to determine if a step is unlocked
  const isStepUnlocked = (stepOrder: number): boolean => {
    if (!isAuthenticated) return true; // Show all steps when not authenticated (no checkboxes)
    if (!stepProgress) return stepOrder === 1; // While loading, only first is unlocked
    
    // Step is unlocked if:
    // 1. It's already completed, OR
    // 2. All previous steps are completed
    if (stepProgress.completed_steps.includes(stepOrder)) return true;
    
    // Check if all previous steps are done
    for (let i = 1; i < stepOrder; i++) {
      if (!stepProgress.completed_steps.includes(i)) return false;
    }
    return true;
  };

  // Calculate progress percentage
  const progressPercentage = stepProgress 
    ? Math.round((stepProgress.completed_steps.length / topic.learning_steps.length) * 100)
    : 0;

  return (
    <div className="space-y-6">
      {/* Learning Steps */}
      {topic.learning_steps.length > 0 && (
        <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-bold text-gray-900 dark:text-white">
              📚 Learning Path
            </h2>
            {isAuthenticated && stepProgress && (
              <span className={`text-sm font-medium px-2 py-1 rounded ${
                progressPercentage === 100
                  ? "bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300"
                  : "bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400"
              }`}>
                {stepProgress.completed_steps.length}/{topic.learning_steps.length} complete
              </span>
            )}
          </div>

          {/* Progress bar */}
          {isAuthenticated && stepProgress && (
            <div className="mb-4">
              <div className="w-full h-2 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
                <div
                  className={`h-full transition-all duration-300 ${
                    progressPercentage === 100 ? "bg-green-500" : "bg-blue-500"
                  }`}
                  style={{ width: `${progressPercentage}%` }}
                />
              </div>
            </div>
          )}

          {loadingSteps ? (
            <div className="flex items-center gap-2 text-gray-500 py-4">
              <svg className="animate-spin w-5 h-5" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
              Loading progress...
            </div>
          ) : (
            <ol className="space-y-4">
              {topic.learning_steps.map((step) => {
                const isCompleted = stepProgress?.completed_steps.includes(step.order) ?? false;
                const isUnlocked = isStepUnlocked(step.order);
                const isToggling = togglingStep === step.order;

                return (
                  <li 
                    key={step.order} 
                    className={`flex items-start gap-3 ${!isUnlocked ? 'opacity-50' : ''}`}
                  >
                    {/* Checkbox or number indicator */}
                    {isAuthenticated ? (
                      <button
                        onClick={() => isUnlocked && handleStepToggle(step.order)}
                        disabled={!isUnlocked || isToggling}
                        className={`flex-shrink-0 w-6 h-6 rounded-full flex items-center justify-center text-sm font-medium mt-0.5 transition-all ${
                          isCompleted
                            ? "bg-green-500 text-white"
                            : isUnlocked
                            ? "bg-blue-100 dark:bg-blue-900 text-blue-600 dark:text-blue-400 hover:bg-blue-200 dark:hover:bg-blue-800 cursor-pointer"
                            : "bg-gray-200 dark:bg-gray-700 text-gray-400 dark:text-gray-500 cursor-not-allowed"
                        }`}
                        title={
                          !isUnlocked 
                            ? "Complete previous steps first" 
                            : isCompleted 
                            ? "Click to uncomplete" 
                            : "Click to mark complete"
                        }
                      >
                        {isToggling ? (
                          <svg className="animate-spin w-4 h-4" viewBox="0 0 24 24">
                            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                          </svg>
                        ) : isCompleted ? (
                          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
                          </svg>
                        ) : isUnlocked ? (
                          step.order
                        ) : (
                          <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
                            <path fillRule="evenodd" d="M5 9V7a5 5 0 0110 0v2a2 2 0 012 2v5a2 2 0 01-2 2H5a2 2 0 01-2-2v-5a2 2 0 012-2zm8-2v2H7V7a3 3 0 016 0z" clipRule="evenodd" />
                          </svg>
                        )}
                      </button>
                    ) : (
                      <span className="flex-shrink-0 w-6 h-6 bg-blue-100 dark:bg-blue-900 text-blue-600 dark:text-blue-400 rounded-full flex items-center justify-center text-sm font-medium mt-0.5">
                        {step.order}
                      </span>
                    )}

                    <div className={`flex-1 min-w-0 ${!isUnlocked ? 'pointer-events-none' : ''}`}>
                      {/* Main step content */}
                      <div className="text-gray-700 dark:text-gray-300">
                        {step.action && (
                          <span className="font-semibold text-gray-900 dark:text-white">{step.action}</span>
                        )}
                        {step.action && (step.title || step.url) && " "}
                        {step.url ? (
                          <a
                            href={step.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-blue-600 hover:text-blue-800 dark:text-blue-400 dark:hover:text-blue-300 hover:underline"
                          >
                            {step.title || step.text}
                          </a>
                        ) : (
                          <span>{step.title || (!step.action ? step.text : "")}</span>
                        )}
                        {/* Inline description after link (no separate description field) */}
                        {!step.description && step.action && !step.title && !step.url && (
                          <span>{step.text.replace(step.action, "").replace(/^[:\s-]+/, "")}</span>
                        )}
                      </div>

                      {/* Description paragraph */}
                      {step.description && (
                        <div className="mt-2 text-sm text-gray-600 dark:text-gray-400">
                          <FormattedDescription text={step.description} />
                          {step.secondary_links && step.secondary_links.length > 0 && (
                            <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1">
                              {step.secondary_links.map((link, i) => (
                                <a
                                  key={i}
                                  href={link.url}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="text-blue-600 hover:text-blue-800 dark:text-blue-400 dark:hover:text-blue-300 hover:underline"
                                >
                                  {link.text}
                                </a>
                              ))}
                            </div>
                          )}
                        </div>
                      )}

                      {/* Code block */}
                      {step.code && (
                        <div className="mt-3 relative">
                          <pre className="bg-gray-900 dark:bg-gray-950 text-gray-100 text-sm p-4 rounded-lg overflow-x-auto">
                            <code>{step.code}</code>
                          </pre>
                          <button
                            onClick={() => navigator.clipboard.writeText(step.code!)}
                            className="absolute top-2 right-2 p-1.5 text-gray-400 hover:text-white bg-gray-800 hover:bg-gray-700 rounded transition-colors"
                            title="Copy to clipboard"
                          >
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
                            </svg>
                          </button>
                        </div>
                      )}

                      {/* Cloud provider options (tabbed interface) */}
                      {step.options && step.options.length > 0 && (
                        <ProviderOptions options={step.options} />
                      )}
                    </div>
                  </li>
                );
              })}
            </ol>
          )}
        </div>
      )}

      {/* Knowledge Questions */}
      {topic.questions && topic.questions.length > 0 && (
        <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-bold text-gray-900 dark:text-white">
              🧠 Test Your Knowledge
            </h2>
            {questionsStatus && (
              <span className={`text-sm font-medium px-2 py-1 rounded ${
                questionsStatus.all_passed 
                  ? "bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300"
                  : "bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400"
              }`}>
                {questionsStatus.passed_questions}/{questionsStatus.total_questions} passed
              </span>
            )}
          </div>
          
          {!isAuthenticated ? (
            <p className="text-gray-600 dark:text-gray-400 text-sm">
              Sign in to answer knowledge questions and track your progress.
            </p>
          ) : loadingQuestions ? (
            <div className="flex items-center gap-2 text-gray-500">
              <svg className="animate-spin w-5 h-5" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
              Loading questions...
            </div>
          ) : (
            <div className="space-y-4">
              {topic.questions.map((question) => {
                const questionStatus = questionsStatus?.questions?.find(
                  (q) => q.question_id === question.id
                );
                return (
                  <KnowledgeQuestion
                    key={question.id}
                    question={question}
                    topicId={topic.id}
                    topicName={topic.name}
                    isPassed={questionStatus?.is_passed ?? false}
                    onPass={handleQuestionPass}
                  />
                );
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
