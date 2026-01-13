"use client";

import Link from "next/link";
import type { TopicWithProgress } from "@/lib/types";

interface TopicCardProps {
  topic: TopicWithProgress;
  phaseSlug?: string;
  isLocked?: boolean;
  previousTopicName?: string;
}

export function TopicCard({ topic, phaseSlug, isLocked = false, previousTopicName }: TopicCardProps) {
  // Use steps + questions for progress
  const stepsCompleted = topic.steps_completed ?? 0;
  const stepsTotal = topic.steps_total ?? 0;
  const questionsCompleted = topic.questions_passed;
  const questionsTotal = topic.questions_total;
  
  const completedCount = stepsCompleted + questionsCompleted;
  const totalCount = stepsTotal + questionsTotal;
  const progressPercent = totalCount > 0 ? (completedCount / totalCount) * 100 : 0;
  const isCompleted = completedCount === totalCount && totalCount > 0;

  // If locked, show locked state
  if (isLocked) {
    return (
      <div className="bg-gray-50 dark:bg-gray-800/50 rounded-lg border border-gray-200 dark:border-gray-700 overflow-hidden opacity-75">
        <div className="p-4">
          <div className="flex items-start justify-between">
            <div className="flex-1">
              <div className="flex items-center gap-2 mb-1">
                <span className="text-sm font-medium text-gray-400 dark:text-gray-500">
                  {topic.order}.
                </span>
                <h4 className="font-medium text-gray-500 dark:text-gray-400">{topic.name}</h4>
                {topic.is_capstone && (
                  <span className="px-2 py-0.5 bg-purple-100 dark:bg-purple-900/50 text-purple-500 dark:text-purple-400 text-xs rounded-full">
                    Capstone
                  </span>
                )}
                <span className="ml-2 text-lg" title="Complete previous topic to unlock">🔒</span>
              </div>
              <p className="text-sm text-gray-400 dark:text-gray-500">{topic.description}</p>
              <p className="text-xs text-gray-400 dark:text-gray-500 mt-2">
                Complete &quot;{previousTopicName}&quot; to unlock this topic
              </p>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <Link
      href={phaseSlug ? `/${phaseSlug}/${topic.slug}` : "#"}
      className="block bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 overflow-hidden hover:border-blue-300 dark:hover:border-blue-600 hover:shadow-md transition-all"
    >
      <div className="p-4">
        <div className="flex items-start justify-between">
          <div className="flex-1">
            <div className="flex items-center gap-2 mb-1">
              <span className="text-sm font-medium text-gray-500 dark:text-gray-400">
                {topic.order}.
              </span>
              <h4 className="font-medium text-gray-900 dark:text-white">{topic.name}</h4>
              {topic.is_capstone && (
                <span className="px-2 py-0.5 bg-purple-100 dark:bg-purple-900 text-purple-700 dark:text-purple-300 text-xs rounded-full">
                  Capstone
                </span>
              )}
              {isCompleted && (
                <span className="ml-2 text-lg" title="Topic completed">✅</span>
              )}
            </div>
            <p className="text-sm text-gray-600 dark:text-gray-300">{topic.description}</p>
            {topic.estimated_time && (
              <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                ⏱️ {topic.estimated_time}
              </p>
            )}
          </div>
          <div className="flex items-center gap-3 ml-4">
            {/* Progress indicator */}
            <div className="text-right">
              <div className="text-sm font-medium text-gray-900 dark:text-white">
                {completedCount}/{totalCount}
              </div>
              <div className="w-20 h-1.5 bg-gray-200 dark:bg-gray-600 rounded-full overflow-hidden">
                <div
                  className={`h-full transition-all duration-300 ${
                    isCompleted ? "bg-green-500" : "bg-blue-500"
                  }`}
                  style={{ width: `${progressPercent}%` }}
                />
              </div>
            </div>
            {/* Arrow to indicate clickable */}
            <svg
              className="w-5 h-5 text-gray-400"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M9 5l7 7-7 7"
              />
            </svg>
          </div>
        </div>
      </div>
    </Link>
  );
}
