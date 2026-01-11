"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import type { TopicWithProgress } from "@/lib/types";
import { useApi } from "@/lib/use-api";

interface TopicCardProps {
  topic: TopicWithProgress;
  phaseSlug?: string;
}

export function TopicCard({ topic, phaseSlug }: TopicCardProps) {
  const router = useRouter();
  const api = useApi();
  const [checklist, setChecklist] = useState(topic.checklist);
  const [isExpanded, setIsExpanded] = useState(false);
  const [updatingItems, setUpdatingItems] = useState<Set<string>>(new Set());

  const handleToggleItem = async (itemId: string) => {
    if (updatingItems.has(itemId)) return;

    setUpdatingItems((prev) => new Set(prev).add(itemId));

    try {
      const result = await api.toggleChecklistItem(itemId);
      setChecklist((prev) =>
        prev.map((item) =>
          item.id === itemId
            ? { ...item, is_completed: result.is_completed }
            : item
        )
      );
      router.refresh();
    } catch (error) {
      console.error("Failed to toggle checklist item:", error);
    } finally {
      setUpdatingItems((prev) => {
        const next = new Set(prev);
        next.delete(itemId);
        return next;
      });
    }
  };

  const completedCount = checklist.filter((item) => item.is_completed).length;
  const totalCount = checklist.length;
  const progressPercent = totalCount > 0 ? (completedCount / totalCount) * 100 : 0;

  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 overflow-hidden">
      {/* Header - always visible */}
      <div className="flex items-center">
        <button
          onClick={() => setIsExpanded(!isExpanded)}
          className="flex-1 p-4 text-left hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
        >
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
                    className="h-full bg-green-500 transition-all duration-300"
                    style={{ width: `${progressPercent}%` }}
                  />
                </div>
              </div>
              {/* Expand/collapse arrow */}
              <svg
                className={`w-5 h-5 text-gray-400 transition-transform ${
                  isExpanded ? "rotate-180" : ""
                }`}
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M19 9l-7 7-7-7"
                />
              </svg>
            </div>
          </div>
        </button>
        {phaseSlug && (
          <Link
            href={`/${phaseSlug}/${topic.slug}`}
            className="px-4 py-2 mr-2 text-sm text-blue-600 hover:text-blue-800 dark:text-blue-400 dark:hover:text-blue-300 hover:bg-blue-50 dark:hover:bg-blue-900/30 rounded-lg transition-colors"
          >
            View →
          </Link>
        )}
      </div>

      {/* Expandable content */}
      {isExpanded && (
        <div className="border-t border-gray-100 dark:border-gray-700">
          {/* Learning Steps */}
          {topic.learning_steps.length > 0 && (
            <div className="p-4 bg-blue-50/50 dark:bg-blue-900/20">
              <h5 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">
                📚 Learning Path
              </h5>
              <ol className="space-y-2">
                {topic.learning_steps.map((step) => (
                  <li key={step.order} className="flex items-start gap-2">
                    <span className="text-sm font-medium text-blue-600 dark:text-blue-400 mt-0.5">
                      {step.order}.
                    </span>
                    <a
                      href={step.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-sm text-blue-600 hover:text-blue-800 dark:text-blue-400 dark:hover:text-blue-300 hover:underline"
                    >
                      {step.text}
                    </a>
                  </li>
                ))}
              </ol>
            </div>
          )}

          {/* Checklist */}
          {checklist.length > 0 && (
            <div className="p-4">
              <h5 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">
                ✅ Checklist
              </h5>
              <ul className="space-y-2">
                {checklist.map((item) => (
                  <li key={item.id} className="flex items-start gap-3">
                    <button
                      onClick={() => handleToggleItem(item.id)}
                      disabled={updatingItems.has(item.id)}
                      className="mt-0.5 flex-shrink-0"
                    >
                      <div
                        className={`w-5 h-5 rounded border-2 flex items-center justify-center transition-colors ${
                          item.is_completed
                            ? "bg-green-500 border-green-500"
                            : "border-gray-300 dark:border-gray-500 hover:border-green-500"
                        } ${updatingItems.has(item.id) ? "opacity-50" : ""}`}
                      >
                        {item.is_completed && (
                          <svg
                            className="w-3 h-3 text-white"
                            fill="none"
                            stroke="currentColor"
                            viewBox="0 0 24 24"
                          >
                            <path
                              strokeLinecap="round"
                              strokeLinejoin="round"
                              strokeWidth={3}
                              d="M5 13l4 4L19 7"
                            />
                          </svg>
                        )}
                      </div>
                    </button>
                    <span
                      className={`text-sm ${
                        item.is_completed
                          ? "text-gray-500 dark:text-gray-400 line-through"
                          : "text-gray-700 dark:text-gray-300"
                      }`}
                    >
                      {item.text}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
