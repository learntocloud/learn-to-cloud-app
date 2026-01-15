"use client";

import Link from "next/link";
import type { PhaseWithProgress } from "@/lib/types";

interface PhaseRoadmapProps {
  phases: PhaseWithProgress[];
}

const PHASE_LABELS = ["Phase 0", "Phase 1", "Phase 2", "Phase 3", "Phase 4", "Phase 5", "Phase 6"];

export function PhaseRoadmap({ phases }: PhaseRoadmapProps) {
  return (
    <div className="space-y-3">
      {phases.map((phase, index) => {
        const isLocked = phase.isLocked;
        const status = phase.progress?.status;
        const isCompleted = status === 'completed';
        const isInProgress = status === 'in_progress';
        const isLast = index === phases.length - 1;
        
        const node = (
          <div className={`flex-1 px-4 py-3 rounded-lg border-2 text-sm font-medium transition-all duration-200 ${
            isLocked 
              ? 'bg-gray-50 dark:bg-gray-800 border-gray-200 dark:border-gray-700 text-gray-400 dark:text-gray-500 cursor-not-allowed' 
              : isCompleted
                ? 'bg-emerald-50 dark:bg-emerald-900/30 border-emerald-400 dark:border-emerald-500 text-emerald-700 dark:text-emerald-300 hover:bg-emerald-100 dark:hover:bg-emerald-900/50 cursor-pointer'
                : isInProgress
                  ? 'bg-amber-50 dark:bg-amber-900/30 border-amber-400 dark:border-amber-500 text-amber-700 dark:text-amber-300 hover:bg-amber-100 dark:hover:bg-amber-900/50 cursor-pointer shadow-sm'
                  : 'bg-white dark:bg-gray-800 border-gray-200 dark:border-gray-700 text-gray-600 dark:text-gray-300 hover:border-gray-300 dark:hover:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-700/50 cursor-pointer'
          }`}>
            <div className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-2 min-w-0">
                {isCompleted && (
                  <svg className="w-4 h-4 text-emerald-500 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                  </svg>
                )}
                {isLocked && (
                  <svg className="w-3.5 h-3.5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
                  </svg>
                )}
                <span className="truncate">{phase.name}</span>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                {isInProgress && phase.progress && (
                  <span className="text-xs text-amber-600 dark:text-amber-400 tabular-nums w-8 text-right">
                    {Math.round(phase.progress.percentage)}%
                  </span>
                )}
                {!isLocked && (
                  <svg className="w-4 h-4 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
                  </svg>
                )}
              </div>
            </div>
            {isInProgress && phase.progress && (
              <div className="mt-2 w-full bg-amber-100 dark:bg-amber-900/30 rounded-full h-1.5 overflow-hidden">
                <div
                  className="h-full bg-amber-500 rounded-full transition-all duration-300"
                  style={{ width: `${phase.progress.percentage}%` }}
                />
              </div>
            )}
          </div>
        );
        
        return (
          <div key={phase.id} className="flex items-stretch gap-4">
            {/* Month label on left */}
            <div className="w-16 shrink-0 flex flex-col items-center">
              <span className="text-xs font-medium text-gray-400 dark:text-gray-500 whitespace-nowrap">
                {PHASE_LABELS[index]}
              </span>
              {/* Connecting line */}
              {!isLast && (
                <div className={`flex-1 w-0.5 mt-2 ${
                  isCompleted 
                    ? 'bg-emerald-300 dark:bg-emerald-600' 
                    : 'bg-gray-200 dark:bg-gray-700'
                }`} />
              )}
            </div>
            
            {/* Phase node */}
            {isLocked ? (
              node
            ) : (
              <Link href={`/${phase.slug}`} className="flex-1">
                {node}
              </Link>
            )}
          </div>
        );
      })}
    </div>
  );
}
