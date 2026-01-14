"use client";

import { useState, useCallback } from "react";
import Link from "next/link";
import type { Topic, TopicWithProgress, LearningObjective } from "@/lib/types";
import { TopicContent } from "./topic-content";

interface TopicPageContentProps {
  topic: Topic | TopicWithProgress;
  phase: {
    id: number;
    name: string;
    slug: string;
  };
  isAuthenticated: boolean;
  prevTopic: { slug: string; name: string } | null;
  nextTopic: { slug: string; name: string } | null;
}

export function TopicPageContent({
  topic,
  phase,
  isAuthenticated,
  prevTopic,
  nextTopic,
}: TopicPageContentProps) {
  // Track step progress locally for real-time UI updates
  const initialStepsCompleted = 'steps_completed' in topic ? topic.steps_completed : 0;
  const initialQuestionsCompleted = 'questions_passed' in topic ? topic.questions_passed : 0;
  
  const [stepsCompleted, setStepsCompleted] = useState(initialStepsCompleted);
  const [questionsCompleted, setQuestionsCompleted] = useState(initialQuestionsCompleted);
  
  const stepsTotal = topic.learning_steps?.length ?? 0;
  const questionsTotal = topic.questions?.length ?? 0;
  
  const totalItems = stepsTotal + questionsTotal;
  const completedItems = stepsCompleted + questionsCompleted;
  const isComplete = completedItems === totalItems && totalItems > 0;
  const percentage = totalItems > 0 ? (completedItems / totalItems) * 100 : 0;

  // Callbacks for child components to update progress
  const onStepProgressChange = useCallback((completed: number) => {
    setStepsCompleted(completed);
  }, []);

  const onQuestionProgressChange = useCallback((completed: number) => {
    setQuestionsCompleted(completed);
  }, []);

  return (
    <>
      {/* Header */}
      <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-8 mb-8">
        <div className="flex items-start justify-between mb-4">
          <div>
            <div className="flex items-center gap-2 mb-2">
              <span className="text-sm font-medium text-gray-500 dark:text-gray-400">
                Topic {topic.order}
              </span>
              {topic.is_capstone && (
                <span className="px-2 py-0.5 bg-purple-100 dark:bg-purple-900 text-purple-700 dark:text-purple-300 text-xs rounded-full">
                  Capstone
                </span>
              )}
            </div>
            <h1 className="text-2xl font-bold text-gray-900 dark:text-white">{topic.name}</h1>
          </div>
        </div>
        
        <p className="text-gray-600 dark:text-gray-300 mb-4">{topic.description}</p>

        {/* What You'll Learn - Learning Objectives */}
        {'learning_objectives' in topic && topic.learning_objectives && topic.learning_objectives.length > 0 && (
          <div className="mb-4 p-4 bg-gradient-to-r from-blue-50 to-indigo-50 dark:from-blue-900/20 dark:to-indigo-900/20 rounded-lg border border-blue-100 dark:border-blue-800/50">
            <h3 className="text-sm font-semibold text-gray-900 dark:text-white mb-2 flex items-center gap-2">
              <svg className="w-4 h-4 text-blue-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              What You&apos;ll Learn
            </h3>
            <ul className="space-y-1">
              {(topic.learning_objectives as LearningObjective[]).map((item) => (
                <li key={item.id} className="flex items-start gap-2 text-sm text-gray-600 dark:text-gray-300">
                  <span className="text-blue-400 mt-1">•</span>
                  <span>{item.text}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        <div className="flex items-center justify-between">
          {topic.estimated_time && (
            <p className="text-sm text-gray-500 dark:text-gray-400 flex items-center gap-1">
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              {topic.estimated_time}
            </p>
          )}
          {isAuthenticated && totalItems > 0 && (
            <span className={`text-sm font-medium px-2 py-1 rounded ${
              isComplete
                ? "bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300"
                : "bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400"
            }`}>
              {completedItems}/{totalItems} complete
            </span>
          )}
        </div>

        {isAuthenticated && totalItems > 0 && (
          <div className="mt-4">
            <div className="w-full h-2 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
              <div
                className={`h-full transition-all duration-300 ${
                  isComplete ? "bg-green-500" : "bg-blue-500"
                }`}
                style={{ width: `${percentage}%` }}
              />
            </div>
          </div>
        )}
      </div>

      {/* Topic Content (Learning Steps & Questions) */}
      <TopicContent 
        topic={topic} 
        isAuthenticated={isAuthenticated}
        onStepProgressChange={onStepProgressChange}
        onQuestionProgressChange={onQuestionProgressChange}
      />

      {/* Sign in prompt for unauthenticated users */}
      {!isAuthenticated && (
        <div className="mt-6 p-4 bg-blue-50 dark:bg-blue-900/30 rounded-lg border border-blue-200 dark:border-blue-800 text-center">
          <p className="text-sm text-blue-700 dark:text-blue-300">
            <Link href="/sign-in" className="font-medium hover:underline">
              Sign in
            </Link>{" "}
            to track your progress and answer knowledge questions
          </p>
        </div>
      )}

      {/* Navigation */}
      <div className="mt-8 flex justify-between">
        {prevTopic ? (
          <Link
            href={`/${phase.slug}/${prevTopic.slug}`}
            className="text-blue-600 hover:text-blue-800 dark:text-blue-400 dark:hover:text-blue-300 font-medium"
          >
            ← {prevTopic.name}
          </Link>
        ) : (
          <div />
        )}
        {nextTopic ? (
          <Link
            href={`/${phase.slug}/${nextTopic.slug}`}
            className="text-blue-600 hover:text-blue-800 dark:text-blue-400 dark:hover:text-blue-300 font-medium"
          >
            {nextTopic.name} →
          </Link>
        ) : (
          <Link
            href={`/${phase.slug}`}
            className="text-blue-600 hover:text-blue-800 dark:text-blue-400 dark:hover:text-blue-300 font-medium"
          >
            Complete Phase: Hands-on Verification →
          </Link>
        )}
      </div>
    </>
  );
}
