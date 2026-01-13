"use client";

import Link from "next/link";
import type { PhaseWithProgress } from "@/lib/types";

interface PhaseCardProps {
  phase: PhaseWithProgress;
  showProgress?: boolean;
}

// Status badge colors
function getStatusStyle(status: string) {
  switch (status) {
    case "completed":
      return "bg-green-100 text-green-700 dark:bg-green-900/50 dark:text-green-300";
    case "in_progress":
      return "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/50 dark:text-yellow-300";
    default:
      return "bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-400";
  }
}

function getStatusLabel(status: string) {
  switch (status) {
    case "completed":
      return "Completed";
    case "in_progress":
      return "In Progress";
    default:
      return "Not Started";
  }
}

export function PhaseCard({ phase, showProgress = false }: PhaseCardProps) {
  const isLocked = phase.isLocked;
  const status = phase.progress?.status;
  
  const cardContent = (
    <div className={`group p-4 rounded-lg border transition-colors ${
      isLocked 
        ? 'border-gray-200 dark:border-gray-700 opacity-50 cursor-not-allowed' 
        : 'border-gray-200 dark:border-gray-700 hover:border-gray-300 dark:hover:border-gray-600 cursor-pointer'
    }`}>
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-3 min-w-0">
          <span className={`text-2xl font-bold ${isLocked ? 'text-gray-300 dark:text-gray-600' : 'text-blue-600 dark:text-blue-400'}`}>
            {phase.id}
          </span>
          <div className="min-w-0">
            <h3 className={`font-medium truncate ${isLocked ? 'text-gray-400 dark:text-gray-500' : 'text-gray-900 dark:text-white'}`}>
              {phase.name} {isLocked && "🔒"}
            </h3>
            <p className="text-xs text-gray-500 dark:text-gray-400">{phase.estimated_weeks}</p>
          </div>
        </div>
        {showProgress && status && !isLocked && (
          <span className={`shrink-0 text-xs px-2 py-0.5 rounded-full ${getStatusStyle(status)}`}>
            {getStatusLabel(status)}
          </span>
        )}
      </div>
      
      {!isLocked && (
        <>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-2 line-clamp-2">
            {phase.description}
          </p>
          <div className="flex items-center justify-between mt-3">
            <span className="text-xs text-gray-400 dark:text-gray-500">
              📚 {phase.topics.length} topics
            </span>
            {showProgress && phase.progress && (
              <div className="flex items-center gap-2">
                <div className="w-16 h-1.5 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
                  <div
                    className={`h-full rounded-full ${status === 'completed' ? 'bg-green-500' : 'bg-blue-500'}`}
                    style={{ width: `${phase.progress.percentage}%` }}
                  />
                </div>
                <span className="text-xs text-gray-400">{Math.round(phase.progress.percentage)}%</span>
              </div>
            )}
          </div>
        </>
      )}
      
      {isLocked && (
        <p className="text-xs text-gray-400 dark:text-gray-500 mt-2">
          Complete Phase {phase.id - 1} to unlock
        </p>
      )}
    </div>
  );
  
  if (isLocked) {
    return cardContent;
  }
  
  return (
    <Link href={`/${phase.slug}`}>
      {cardContent}
    </Link>
  );
}
