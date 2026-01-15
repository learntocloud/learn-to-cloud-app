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
    <div className={`group p-5 rounded-xl border transition-all duration-200 ${
      isLocked
        ? 'bg-gray-50 dark:bg-gray-800/30 border-gray-200 dark:border-gray-700 opacity-60 cursor-not-allowed'
        : 'bg-white dark:bg-gray-800/50 border-gray-200 dark:border-gray-700 hover:border-blue-300 dark:hover:border-blue-600 hover:shadow-md cursor-pointer'
    }`}>
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-4 min-w-0">
          <div className={`w-12 h-12 rounded-xl flex items-center justify-center text-xl font-bold ${
            isLocked
              ? 'bg-gray-100 dark:bg-gray-700 text-gray-400 dark:text-gray-500'
              : status === 'completed'
                ? 'bg-gradient-to-br from-green-400 to-emerald-500 text-white shadow-sm'
                : status === 'in_progress'
                  ? 'bg-gradient-to-br from-blue-400 to-blue-600 text-white shadow-sm'
                  : 'bg-gradient-to-br from-gray-100 to-gray-200 dark:from-gray-700 dark:to-gray-600 text-gray-600 dark:text-gray-300'
          }`}>
            {phase.id}
          </div>
          <div className="min-w-0">
            <h3 className={`font-semibold text-base ${isLocked ? 'text-gray-400 dark:text-gray-500' : 'text-gray-900 dark:text-white'}`}>
              {phase.name} {isLocked && "🔒"}
            </h3>
            <p className="text-sm text-gray-500 dark:text-gray-400">{phase.estimated_weeks}</p>
          </div>
        </div>
        {showProgress && status && !isLocked && (
          <span className={`shrink-0 text-xs px-2.5 py-1 rounded-full font-medium ${getStatusStyle(status)}`}>
            {getStatusLabel(status)}
          </span>
        )}
      </div>

      {!isLocked && showProgress && phase.progress && (
        <div className="flex items-center justify-end gap-2 mt-4">
          <div className="w-24 h-2 bg-gray-100 dark:bg-gray-700 rounded-full overflow-hidden">
            <div
              className={`h-full rounded-full transition-all duration-300 ${status === 'completed' ? 'bg-gradient-to-r from-green-400 to-emerald-500' : 'bg-gradient-to-r from-blue-400 to-blue-600'}`}
              style={{ width: `${phase.progress.percentage}%` }}
            />
          </div>
          <span className="text-sm font-medium text-gray-600 dark:text-gray-300">{Math.round(phase.progress.percentage)}%</span>
        </div>
      )}

      {isLocked && (
        <p className="text-sm text-gray-400 dark:text-gray-500 mt-3">
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
