"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { useApi } from "@/lib/use-api";

interface DailyReflectionProps {
  userName?: string;
  existingReflection?: string;
  onSubmit?: () => void;
}

const MAX_CHARS = 1000;
const MIN_CHARS = 10;

const PROMPTS = [
  "What's one thing you learned today that surprised you?",
  "What concept are you still trying to wrap your head around?",
  "Did you have any 'aha!' moments today?",
  "What would you teach someone about what you learned?",
  "What's your next learning goal?",
];

export function DailyReflection({ userName, existingReflection, onSubmit }: DailyReflectionProps) {
  const router = useRouter();
  const api = useApi();
  
  const [reflection, setReflection] = useState(existingReflection || "");
  const [savedReflection, setSavedReflection] = useState(existingReflection || "");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isSubmitted, setIsSubmitted] = useState(!!existingReflection);
  const [isExpanded, setIsExpanded] = useState(!existingReflection);
  const [isLoading, setIsLoading] = useState(!existingReflection);
  const [error, setError] = useState<string | null>(null);

  // Fetch today's reflection on mount if not provided
  useEffect(() => {
    if (!existingReflection) {
      api.getTodayReflection()
        .then((data) => {
          if (data?.reflection_text) {
            setReflection(data.reflection_text);
            setSavedReflection(data.reflection_text);
            setIsSubmitted(true);
            setIsExpanded(false);
          }
        })
        .catch(() => {
          // No reflection for today, that's fine
        })
        .finally(() => {
          setIsLoading(false);
        });
    } else {
      setIsLoading(false);
    }
  }, [existingReflection]);

  const dailyPrompt = PROMPTS[new Date().getDay() % PROMPTS.length];

  const handleSubmit = async () => {
    if (reflection.length < MIN_CHARS) {
      setError(`At least ${MIN_CHARS} characters needed`);
      return;
    }

    setIsSubmitting(true);
    setError(null);

    try {
      await api.submitReflection(reflection);
      setIsSubmitted(true);
      setSavedReflection(reflection);
      setIsExpanded(false);
      onSubmit?.();
      router.refresh();
    } catch (err) {
      console.error("Failed to submit reflection:", err);
      setError("Failed to save. Please try again.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleCancel = () => {
    setReflection(savedReflection);
    setIsExpanded(false);
    setError(null);
  };

  const charCount = reflection.length;
  const isOverLimit = charCount > MAX_CHARS;
  const canSubmit = charCount >= MIN_CHARS && !isOverLimit && !isSubmitting;

  // Loading - minimal skeleton
  if (isLoading) {
    return (
      <div className="mb-6 h-12 bg-gray-100 dark:bg-gray-800 rounded-lg animate-pulse" />
    );
  }

  // Collapsed - minimal single line
  if (isSubmitted && !isExpanded) {
    return (
      <button
        onClick={() => setIsExpanded(true)}
        className="w-full mb-6 px-4 py-3 bg-gray-50 dark:bg-gray-800/50 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 transition-colors text-left group"
      >
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 text-sm text-gray-600 dark:text-gray-400">
            <span className="text-green-500">✓</span>
            <span>Today's reflection saved</span>
            <span className="text-gray-400 dark:text-gray-500">·</span>
            <span className="truncate max-w-[300px] text-gray-500 dark:text-gray-500">
              {savedReflection}
            </span>
          </div>
          <span className="text-xs text-gray-400 group-hover:text-gray-600 dark:group-hover:text-gray-300">
            Edit
          </span>
        </div>
      </button>
    );
  }

  // Expanded - clean form
  return (
    <div className="mb-6 p-4 bg-gray-50 dark:bg-gray-800/50 rounded-lg border border-gray-200 dark:border-gray-700">
      <div className="flex items-center justify-between mb-3">
        <p className="text-sm text-gray-600 dark:text-gray-400">
          💭 {dailyPrompt}
        </p>
        {savedReflection && (
          <button
            onClick={handleCancel}
            className="text-xs text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
          >
            Cancel
          </button>
        )}
      </div>

      <textarea
        value={reflection}
        onChange={(e) => {
          setReflection(e.target.value);
          setError(null);
        }}
        placeholder="Share your thoughts..."
        rows={2}
        maxLength={MAX_CHARS + 100}
        disabled={isSubmitting}
        className="w-full px-3 py-2 text-sm bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-600 rounded-lg resize-none focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 placeholder-gray-400 dark:placeholder-gray-500 disabled:opacity-50"
      />

      <div className="flex items-center justify-between mt-2">
        <div className="text-xs text-gray-400">
          {error ? (
            <span className="text-red-500">{error}</span>
          ) : charCount < MIN_CHARS ? (
            `${MIN_CHARS - charCount} more characters`
          ) : (
            <span className="text-gray-400">{charCount}/{MAX_CHARS}</span>
          )}
        </div>
        <button
          onClick={handleSubmit}
          disabled={!canSubmit}
          className={`px-3 py-1.5 text-sm font-medium rounded-lg transition-colors ${
            canSubmit
              ? "bg-blue-600 hover:bg-blue-700 text-white"
              : "bg-gray-200 dark:bg-gray-700 text-gray-400 cursor-not-allowed"
          }`}
        >
          {isSubmitting ? "Saving..." : savedReflection ? "Update" : "Save"}
        </button>
      </div>
    </div>
  );
}
