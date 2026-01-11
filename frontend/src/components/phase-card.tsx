"use client";

import Link from "next/link";
import type { PhaseWithProgress } from "@/lib/types";
import { ProgressBar, StatusBadge } from "./progress";

interface PhaseCardProps {
  phase: PhaseWithProgress;
  showProgress?: boolean;
}

export function PhaseCard({ phase, showProgress = false }: PhaseCardProps) {
  const isLocked = phase.isLocked;
  
  const cardContent = (
    <div className={`bg-white dark:bg-gray-800 rounded-xl border ${isLocked ? 'border-gray-300 dark:border-gray-600 opacity-60' : 'border-gray-200 dark:border-gray-700 hover:shadow-lg hover:border-blue-300'} p-6 transition-all ${isLocked ? 'cursor-not-allowed' : 'cursor-pointer'} h-full relative`}>
      {isLocked && (
        <div className="absolute top-4 right-4">
          <span className="text-2xl" title="Complete the previous phase to unlock">🔒</span>
        </div>
      )}
      <div className="flex items-start justify-between mb-4">
        <div className="flex items-center gap-3">
          <span className={`text-3xl font-bold ${isLocked ? 'text-gray-400' : 'text-blue-600'}`}>{phase.id}</span>
          <div>
            <h3 className={`font-semibold text-lg ${isLocked ? 'text-gray-500 dark:text-gray-400' : 'text-gray-900 dark:text-white'}`}>{phase.name}</h3>
            <p className="text-sm text-gray-500 dark:text-gray-400">{phase.estimated_weeks}</p>
          </div>
        </div>
        {showProgress && phase.progress && !isLocked && (
          <StatusBadge status={phase.progress.status} />
        )}
      </div>
      
      <p className={`${isLocked ? 'text-gray-400 dark:text-gray-500' : 'text-gray-600 dark:text-gray-300'} text-sm mb-4 line-clamp-2`}>{phase.description}</p>
      
      <div className="flex items-center gap-4 text-sm text-gray-500 dark:text-gray-400 mb-4">
        <span className="flex items-center gap-1">
          📚 {phase.topics.length} topics
        </span>
      </div>
      
      {isLocked ? (
        <div className="text-sm text-gray-400 dark:text-gray-500 italic">
          Complete Phase {phase.id - 1} to unlock
        </div>
      ) : (
        showProgress && phase.progress && (
          <ProgressBar percentage={phase.progress.percentage} size="sm" />
        )
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
