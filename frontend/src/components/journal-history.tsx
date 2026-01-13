"use client";

import { useState } from "react";
import type { ReflectionEntry } from "@/lib/api";

interface JournalHistoryProps {
  entries: ReflectionEntry[];
}

function formatDate(dateStr: string): string {
  const date = new Date(dateStr + "T00:00:00");
  const today = new Date();
  const yesterday = new Date(today);
  yesterday.setDate(yesterday.getDate() - 1);
  
  if (date.toDateString() === today.toDateString()) {
    return "Today";
  }
  if (date.toDateString() === yesterday.toDateString()) {
    return "Yesterday";
  }
  
  return date.toLocaleDateString("en-US", { 
    weekday: "short",
    month: "short", 
    day: "numeric",
  });
}

function getRelativeTime(dateStr: string): string {
  const date = new Date(dateStr + "T00:00:00");
  const now = new Date();
  const diffDays = Math.floor((now.getTime() - date.getTime()) / (1000 * 60 * 60 * 24));
  
  if (diffDays === 0) return "today";
  if (diffDays === 1) return "1 day ago";
  if (diffDays < 7) return `${diffDays} days ago`;
  if (diffDays < 30) return `${Math.floor(diffDays / 7)} week${Math.floor(diffDays / 7) > 1 ? 's' : ''} ago`;
  return `${Math.floor(diffDays / 30)} month${Math.floor(diffDays / 30) > 1 ? 's' : ''} ago`;
}

export function JournalHistory({ entries }: JournalHistoryProps) {
  const [expandedId, setExpandedId] = useState<number | null>(null);
  
  // Skip today's entry (shown separately)
  const today = new Date().toISOString().split("T")[0];
  const pastEntries = entries.filter(e => e.reflection_date !== today);
  
  if (pastEntries.length === 0) {
    return null;
  }

  return (
    <div className="space-y-3">
      {pastEntries.map((entry) => {
        const isExpanded = expandedId === entry.id;
        const preview = entry.reflection_text.length > 150 
          ? entry.reflection_text.slice(0, 150) + "..." 
          : entry.reflection_text;
        
        return (
          <div
            key={entry.id}
            className="group"
          >
            <button
              onClick={() => setExpandedId(isExpanded ? null : entry.id)}
              className="w-full text-left p-4 rounded-lg border border-gray-200 dark:border-gray-700 hover:border-gray-300 dark:hover:border-gray-600 transition-colors"
            >
              <div className="flex items-start justify-between gap-4">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-sm font-medium text-gray-700 dark:text-gray-300">
                      {formatDate(entry.reflection_date)}
                    </span>
                    <span className="text-xs text-gray-400 dark:text-gray-500">
                      {getRelativeTime(entry.reflection_date)}
                    </span>
                  </div>
                  <p className="text-sm text-gray-600 dark:text-gray-400">
                    {isExpanded ? entry.reflection_text : preview}
                  </p>
                </div>
                <svg
                  className={`w-4 h-4 text-gray-400 shrink-0 transition-transform ${isExpanded ? 'rotate-180' : ''}`}
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                </svg>
              </div>
            </button>
          </div>
        );
      })}
    </div>
  );
}
