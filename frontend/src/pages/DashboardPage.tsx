import { Link, Navigate } from 'react-router-dom';
import { useUser } from '@clerk/clerk-react';
import { useDashboard, useStreak } from '@/lib/hooks';
import type { PhaseSummarySchema } from '@/lib/api-client';

export function DashboardPage() {
  const { isSignedIn, isLoaded } = useUser();

  if (isLoaded && !isSignedIn) {
    return <Navigate to="/" replace />;
  }

  return (
    <div className="py-8 bg-gradient-to-b from-gray-50 to-white dark:from-gray-900 dark:to-gray-950">
      <div className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8">
        {isLoaded && isSignedIn && <DashboardContent />}
      </div>
    </div>
  );
}

function DashboardContent() {
  const { data: dashboard, isLoading: dashboardLoading, error: dashboardError } = useDashboard();
  const { data: streakData } = useStreak();

  if (dashboardLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  if (dashboardError || !dashboard) {
    return (
      <div className="text-center py-20">
        <p className="text-red-500">Failed to load dashboard. Please try again.</p>
      </div>
    );
  }

  return (
    <>
      {/* Combined Header + Progress */}
      <div className="bg-white dark:bg-gray-800/50 rounded-2xl border border-gray-200 dark:border-gray-700 p-5 mb-6 shadow-sm">
        <div className="flex items-start justify-between gap-4 mb-4">
          <div>
            <h1 className="text-xl font-bold text-gray-900 dark:text-white">
              {dashboard.user.first_name ? `Welcome back, ${dashboard.user.first_name}` : "Welcome back"} 👋
            </h1>
            <p className="text-sm text-gray-500 dark:text-gray-400 mt-0.5">
              Keep up the great work on your cloud journey!
            </p>
          </div>

          {streakData && streakData.current_streak > 0 && (
            <span className="text-orange-500 dark:text-orange-400 text-sm font-medium shrink-0">
              🔥 {streakData.current_streak} day streak
            </span>
          )}
        </div>

        {/* Progress bar */}
        <div className="flex items-center gap-3">
          <div className="flex-1 bg-gray-100 dark:bg-gray-700 rounded-full h-2 overflow-hidden">
            <div
              className="bg-emerald-500 h-2 rounded-full transition-all duration-500"
              style={{ width: `${dashboard.overall_progress}%` }}
            />
          </div>
          <div className="text-right shrink-0">
            <span className="text-sm font-semibold text-gray-700 dark:text-gray-300 tabular-nums">
              {dashboard.phases_completed}/{dashboard.phases_total} phases
            </span>
            <Link
              to="/certificates"
              className="block text-xs font-medium text-amber-600 dark:text-amber-400 hover:text-amber-700 dark:hover:text-amber-300 transition-colors mt-0.5"
            >
              🏆 View Certificate
            </Link>
          </div>
        </div>
      </div>

      {/* Phases Section */}
      <div className="mb-6">
        <h2 className="text-base font-semibold text-gray-900 dark:text-white mb-4">
          Your Journey
        </h2>
        <PhaseRoadmap phases={dashboard.phases} />
      </div>
    </>
  );
}

const PHASE_LABELS = ["Phase 0", "Phase 1", "Phase 2", "Phase 3", "Phase 4", "Phase 5", "Phase 6"];

function PhaseRoadmap({ phases }: { phases: PhaseSummarySchema[] }) {
  return (
    <div className="space-y-3">
      {phases.map((phase, index) => {
        const isLocked = phase.is_locked;
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
              <Link to={`/${phase.slug}`} className="flex-1">
                {node}
              </Link>
            )}
          </div>
        );
      })}
    </div>
  );
}
