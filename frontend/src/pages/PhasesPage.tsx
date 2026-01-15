import { Link } from 'react-router-dom';
import { usePhasesWithProgress } from '@/lib/hooks';
import type { PhaseSummarySchema } from '@/lib/api-client';

export function PhasesPage() {
  const { data: phases, isLoading, error } = usePhasesWithProgress();

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  if (error || !phases) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <p className="text-red-500">Failed to load phases. Please try again.</p>
      </div>
    );
  }

  return (
    <div className="min-h-screen py-8">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        {/* Header */}
        <div className="mb-10 text-center">
          <h1 className="text-3xl md:text-4xl font-bold text-gray-900 dark:text-white">
            Your Cloud Engineering Journey
          </h1>
          <p className="text-gray-600 dark:text-gray-300 mt-3 text-lg max-w-2xl mx-auto">
            A structured roadmap to take you from beginner to cloud professional. 
            Complete each phase to unlock the next.
          </p>
        </div>

        {/* Journey Timeline */}
        <div className="relative">
          {/* Vertical Progress Line */}
          <div className="absolute left-7 md:left-9 top-0 bottom-0 w-0.5 bg-gradient-to-b from-blue-500 via-blue-400 to-blue-300 hidden sm:block" />

          <div className="space-y-0">
            {phases.map((phase, index) => (
              <PhaseCard key={phase.id} phase={phase} isLast={index === phases.length - 1} />
            ))}
          </div>
        </div>

        {/* CTA at bottom */}
        <div className="mt-12 text-center">
          <p className="text-gray-500 dark:text-gray-400 mb-4">
            Ready to start your journey?
          </p>
          <Link
            to="/phase0"
            className="inline-flex items-center gap-2 px-6 py-3 bg-blue-600 hover:bg-blue-700 text-white font-medium rounded-lg transition-colors"
          >
            Start with Phase 0
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7l5 5m0 0l-5 5m5-5H6" />
            </svg>
          </Link>
        </div>
      </div>
    </div>
  );
}

function PhaseCard({ phase, isLast }: { phase: PhaseSummarySchema; isLast: boolean }) {
  return (
    <div className="relative">
      {/* Phase Card */}
      <div className="sm:pl-20 md:pl-24 pb-8">
        {/* Timeline Node - visible on sm+ */}
        <div className="absolute left-4 md:left-6 hidden sm:flex items-center justify-center">
          <div className="w-7 h-7 md:w-7 md:h-7 rounded-full bg-blue-500 text-white flex items-center justify-center text-sm font-bold shadow-lg ring-4 ring-white dark:ring-gray-900">
            {phase.id}
          </div>
        </div>

        <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5 md:p-6 hover:shadow-xl hover:border-blue-400 dark:hover:border-blue-500 transition-all duration-200 group">
          <div className="flex flex-col md:flex-row md:items-start gap-4">
            {/* Mobile Phase Number */}
            <div className="flex items-center gap-3 sm:hidden">
              <span className="inline-flex items-center justify-center w-10 h-10 rounded-full bg-blue-500 text-white text-lg font-bold">
                {phase.id}
              </span>
              <div>
                <Link to={`/${phase.slug}`} className="text-lg font-semibold text-gray-900 dark:text-white hover:text-blue-600 dark:hover:text-blue-400">
                  {phase.name}
                </Link>
                <p className="text-xs text-gray-500 dark:text-gray-400">{phase.estimated_weeks}</p>
              </div>
            </div>

            {/* Desktop Header */}
            <div className="flex-1">
              <div className="hidden sm:flex items-center gap-3 mb-2">
                <Link to={`/${phase.slug}`} className="text-xl font-semibold text-gray-900 dark:text-white hover:text-blue-600 dark:hover:text-blue-400 transition-colors">
                  {phase.name}
                </Link>
                <span className="text-xs text-gray-500 dark:text-gray-400 bg-gray-100 dark:bg-gray-700 px-2 py-0.5 rounded">
                  {phase.estimated_weeks}
                </span>
                <span className="text-xs text-blue-600 dark:text-blue-400 bg-blue-50 dark:bg-blue-900/30 px-2 py-0.5 rounded">
                  {phase.topics_count} topics
                </span>
              </div>

              {/* Description */}
              <p className="text-gray-600 dark:text-gray-300 text-sm md:text-base mb-4">
                {phase.short_description}
              </p>
            </div>

            {/* Arrow - links to phase */}
            <Link to={`/${phase.slug}`} className="hidden md:flex items-center self-center text-gray-400 hover:text-blue-500 transition-colors">
              <svg className="w-6 h-6 transform hover:translate-x-1 transition-transform" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
              </svg>
            </Link>
          </div>
        </div>
      </div>

      {/* Connector dot at the end */}
      {isLast && (
        <div className="absolute left-4 md:left-6 bottom-0 hidden sm:flex items-center justify-center">
          <div className="w-4 h-4 rounded-full bg-green-500 shadow-lg ring-4 ring-white dark:ring-gray-900">
            <svg className="w-4 h-4 text-white p-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
            </svg>
          </div>
        </div>
      )}
    </div>
  );
}
