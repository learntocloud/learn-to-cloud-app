"use client";

import { useState, useEffect } from "react";
import type { Topic, TopicWithProgress, TopicQuestionsStatus } from "@/lib/types";
import { useApi } from "@/lib/use-api";
import { KnowledgeQuestion } from "./knowledge-question";
import { ProviderOptions } from "./provider-options";

interface TopicContentProps {
  topic: Topic | TopicWithProgress;
  isAuthenticated: boolean;
}

export function TopicContent({ topic, isAuthenticated }: TopicContentProps) {
  const api = useApi();
  
  // State for knowledge questions
  const [questionsStatus, setQuestionsStatus] = useState<TopicQuestionsStatus | null>(null);
  const [loadingQuestions, setLoadingQuestions] = useState(false);

  // Fetch question status for authenticated users
  useEffect(() => {
    if (isAuthenticated && topic.questions && topic.questions.length > 0) {
      setLoadingQuestions(true);
      api.getTopicQuestionsStatus(topic.id)
        .then((status) => {
          setQuestionsStatus(status);
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
        })
        .catch((err) => {
          console.error("Failed to refresh question status:", err);
        });
    }
  };

  return (
    <div className="space-y-6">
      {/* Learning Steps */}
      {topic.learning_steps.length > 0 && (
        <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-6">
          <h2 className="text-lg font-bold text-gray-900 dark:text-white mb-4">
            📚 Learning Path
          </h2>
          <ol className="space-y-4">
            {topic.learning_steps.map((step) => (
              <li key={step.order} className="flex items-start gap-3">
                <span className="flex-shrink-0 w-6 h-6 bg-blue-100 dark:bg-blue-900 text-blue-600 dark:text-blue-400 rounded-full flex items-center justify-center text-sm font-medium mt-0.5">
                  {step.order}
                </span>
                <div className="flex-1 min-w-0">
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
                    <p className="mt-2 text-sm text-gray-600 dark:text-gray-400">
                      {step.description}
                      {step.secondary_links?.map((link, i) => (
                        <span key={i}>
                          {" "}
                          <a
                            href={link.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-blue-600 hover:text-blue-800 dark:text-blue-400 dark:hover:text-blue-300 hover:underline"
                          >
                            {link.text}
                          </a>
                        </span>
                      ))}
                    </p>
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
            ))}
          </ol>
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
