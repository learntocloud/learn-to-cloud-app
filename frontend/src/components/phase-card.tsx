"use client";

import Link from "next/link";
import type { PhaseWithProgress } from "@/lib/types";
import { ProgressBar, StatusBadge } from "./progress";

interface PhaseCardProps {
  phase: PhaseWithProgress;
  showProgress?: boolean;
}

export function PhaseCard({ phase, showProgress = false }: PhaseCardProps) {
  return (
    <Link href={`/${phase.slug}`}>
      <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-6 hover:shadow-lg hover:border-blue-300 transition-all cursor-pointer h-full">
        <div className="flex items-start justify-between mb-4">
          <div className="flex items-center gap-3">
            <span className="text-3xl font-bold text-blue-600">{phase.id}</span>
            <div>
              <h3 className="font-semibold text-lg text-gray-900 dark:text-white">{phase.name}</h3>
              <p className="text-sm text-gray-500 dark:text-gray-400">{phase.estimated_weeks}</p>
            </div>
          </div>
          {showProgress && phase.progress && (
            <StatusBadge status={phase.progress.status} />
          )}
        </div>
        
        <p className="text-gray-600 dark:text-gray-300 text-sm mb-4 line-clamp-2">{phase.description}</p>
        
        <div className="flex items-center gap-4 text-sm text-gray-500 dark:text-gray-400 mb-4">
          <span className="flex items-center gap-1">
            📚 {phase.topics.length} topics
          </span>
          <span className="flex items-center gap-1">
            ✅ {phase.checklist.length} checklist items
          </span>
        </div>
        
        {showProgress && phase.progress && (
          <ProgressBar percentage={phase.progress.percentage} size="sm" />
        )}
      </div>
    </Link>
  );
}
