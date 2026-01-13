"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useApi } from "@/lib/use-api";

interface JournalEntryProps {
  prompt: string;
  existingReflection?: string;
  currentPhase: number | null;
}

const MAX_CHARS = 2000;
const MIN_CHARS = 10;

export function JournalEntry({ prompt, existingReflection, currentPhase }: JournalEntryProps) {
  const router = useRouter();
  const api = useApi();
  
  const [reflection, setReflection] = useState(existingReflection || "");
  const [savedReflection, setSavedReflection] = useState(existingReflection || "");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isSaved, setIsSaved] = useState(!!existingReflection);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async () => {
    if (reflection.length < MIN_CHARS) {
      setError(`Write at least ${MIN_CHARS} characters`);
      return;
    }

    setIsSubmitting(true);
    setError(null);

    try {
      await api.submitReflection(reflection);
      setIsSaved(true);
      setSavedReflection(reflection);
      router.refresh();
    } catch (err) {
      console.error("Failed to save reflection:", err);
      setError("Failed to save. Please try again.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const charCount = reflection.length;
  const isOverLimit = charCount > MAX_CHARS;
  const hasChanges = reflection !== savedReflection;
  const canSubmit = charCount >= MIN_CHARS && !isOverLimit && !isSubmitting && hasChanges;

  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 overflow-hidden">
      {/* Prompt */}
      <div className="px-4 py-3 bg-gray-50 dark:bg-gray-800/50 border-b border-gray-200 dark:border-gray-700">
        <p className="text-sm text-gray-600 dark:text-gray-400">
          💭 {prompt}
        </p>
      </div>

      {/* Editor */}
      <div className="p-4">
        <textarea
          value={reflection}
          onChange={(e) => {
            setReflection(e.target.value);
            setError(null);
          }}
          placeholder="Write your thoughts..."
          rows={6}
          maxLength={MAX_CHARS + 100}
          disabled={isSubmitting}
          className="w-full bg-transparent border-0 resize-none focus:outline-none focus:ring-0 placeholder-gray-400 dark:placeholder-gray-500 text-gray-900 dark:text-white disabled:opacity-50"
        />
      </div>

      {/* Footer */}
      <div className="px-4 py-3 bg-gray-50 dark:bg-gray-800/50 border-t border-gray-200 dark:border-gray-700 flex items-center justify-between">
        <div className="text-xs text-gray-400">
          {error ? (
            <span className="text-red-500">{error}</span>
          ) : isSaved && !hasChanges ? (
            <span className="text-green-600 dark:text-green-400">✓ Saved</span>
          ) : charCount < MIN_CHARS ? (
            `${MIN_CHARS - charCount} more characters needed`
          ) : (
            `${charCount}/${MAX_CHARS}`
          )}
        </div>
        
        <button
          onClick={handleSubmit}
          disabled={!canSubmit}
          className={`px-4 py-2 text-sm font-medium rounded-lg transition-colors ${
            canSubmit
              ? "bg-blue-600 hover:bg-blue-700 text-white"
              : "bg-gray-100 dark:bg-gray-700 text-gray-400 cursor-not-allowed"
          }`}
        >
          {isSubmitting ? "Saving..." : savedReflection ? "Update" : "Save Reflection"}
        </button>
      </div>
    </div>
  );
}
