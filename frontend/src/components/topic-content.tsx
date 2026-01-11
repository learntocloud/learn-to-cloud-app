"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import type { Topic, TopicWithProgress, TopicChecklistItemWithProgress } from "@/lib/types";
import { useApi } from "@/lib/use-api";

interface TopicContentProps {
  topic: Topic | TopicWithProgress;
  isAuthenticated: boolean;
}

export function TopicContent({ topic, isAuthenticated }: TopicContentProps) {
  const router = useRouter();
  const api = useApi();
  
  // Only manage state for authenticated users
  const initialChecklist = 'items_completed' in topic 
    ? (topic as TopicWithProgress).checklist 
    : topic.checklist.map(item => ({ ...item, is_completed: false, completed_at: null }));
  
  const [checklist, setChecklist] = useState<TopicChecklistItemWithProgress[]>(initialChecklist as TopicChecklistItemWithProgress[]);
  const [updatingItems, setUpdatingItems] = useState<Set<string>>(new Set());

  const handleToggleItem = async (itemId: string) => {
    if (!isAuthenticated || updatingItems.has(itemId)) return;

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

  return (
    <div className="space-y-6">
      {/* Learning Steps */}
      {topic.learning_steps.length > 0 && (
        <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-6">
          <h2 className="text-lg font-bold text-gray-900 dark:text-white mb-4">
            📚 Learning Path
          </h2>
          <ol className="space-y-3">
            {topic.learning_steps.map((step) => (
              <li key={step.order} className="flex items-start gap-3">
                <span className="flex-shrink-0 w-6 h-6 bg-blue-100 dark:bg-blue-900 text-blue-600 dark:text-blue-400 rounded-full flex items-center justify-center text-sm font-medium">
                  {step.order}
                </span>
                <a
                  href={step.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-blue-600 hover:text-blue-800 dark:text-blue-400 dark:hover:text-blue-300 hover:underline"
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
        <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-6">
          <h2 className="text-lg font-bold text-gray-900 dark:text-white mb-4">
            ✅ Checklist
          </h2>
          <ul className="space-y-3">
            {checklist.map((item) => (
              <li key={item.id} className="flex items-start gap-3">
                {isAuthenticated ? (
                  <button
                    onClick={() => handleToggleItem(item.id)}
                    disabled={updatingItems.has(item.id)}
                    className="mt-0.5 flex-shrink-0"
                  >
                    <div
                      className={`w-6 h-6 rounded border-2 flex items-center justify-center transition-colors ${
                        item.is_completed
                          ? "bg-green-500 border-green-500"
                          : "border-gray-300 dark:border-gray-500 hover:border-green-500"
                      } ${updatingItems.has(item.id) ? "opacity-50" : ""}`}
                    >
                      {item.is_completed && (
                        <svg
                          className="w-4 h-4 text-white"
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
                ) : (
                  <div className="mt-0.5 flex-shrink-0 w-6 h-6 rounded border-2 border-gray-300 dark:border-gray-500" />
                )}
                <span
                  className={`${
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
  );
}
