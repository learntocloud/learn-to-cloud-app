import { useState } from 'react';
import { Link } from 'react-router-dom';
import { usePhasesWithProgress } from '@/lib/hooks';
import type { PhaseSummarySchema } from '@/lib/api-client';

export function PhasesPage() {
  const { data: phases, isLoading, error } = usePhasesWithProgress();
  const [openSlugs, setOpenSlugs] = useState<Set<string>>(() => new Set());

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
      <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8">
        {/* Header */}
        <div className="mb-10 text-center">
          <h1 className="text-3xl md:text-4xl font-bold text-gray-900 dark:text-white">
            Your Cloud Engineering Journey
          </h1>
          <p className="text-gray-600 dark:text-gray-300 mt-3 text-lg max-w-2xl mx-auto">
            A curated curriculum overview to help you understand what you'll learn and how the projects build over time.
          </p>
          <div className="mt-6">
            <Link
              to="/phase0"
              className="inline-flex items-center gap-2 px-6 py-3 bg-blue-600 hover:bg-blue-700 text-white font-medium rounded-lg transition-colors"
            >
              Get Started
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7l5 5m0 0l-5 5m5-5H6" />
              </svg>
            </Link>
          </div>
        </div>

        {/* Journey Timeline */}
        <div className="relative">
          <div className="absolute left-6 top-0 bottom-0 w-0.5 bg-gradient-to-b from-blue-500 via-blue-400 to-blue-300 hidden sm:block" />
          <div className="space-y-4">
            {phases.map((phase) => (
              <PhaseAccordionItem
                key={phase.id}
                phase={phase}
                isOpen={openSlugs.has(phase.slug)}
                onToggle={() => {
                  setOpenSlugs((prev) => {
                    const next = new Set(prev);
                    if (next.has(phase.slug)) {
                      next.delete(phase.slug);
                    } else {
                      next.add(phase.slug);
                    }
                    return next;
                  });
                }}
              />
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
function PhaseAccordionItem({
  phase,
  isOpen,
  onToggle,
}: {
  phase: PhaseSummarySchema;
  isOpen: boolean;
  onToggle: () => void;
}) {
  return (
    <div className="relative sm:pl-14">
      {/* Timeline node */}
      <div className="absolute left-2 top-6 hidden sm:flex items-center justify-center">
        <div className="w-9 h-9 rounded-full bg-blue-600 text-white flex items-center justify-center text-sm font-bold shadow-lg ring-4 ring-white dark:ring-gray-900">
          {phase.id}
        </div>
      </div>

      <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 overflow-hidden">
        <button
          type="button"
          onClick={onToggle}
          className="w-full text-left p-5 md:p-6 hover:bg-gray-50 dark:hover:bg-gray-800/70 transition-colors"
          aria-expanded={isOpen}
        >
          <div className="flex items-start gap-4">
            <div className="shrink-0 sm:hidden">
              <div className="inline-flex items-center justify-center w-11 h-11 rounded-full text-lg font-bold shadow-sm bg-blue-600 text-white">
                {phase.id}
              </div>
            </div>

            <div className="flex-1 min-w-0">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <h2 className="text-lg sm:text-xl font-semibold text-gray-900 dark:text-white truncate">
                    {phase.name}
                  </h2>
                  <p className="text-xs sm:text-sm text-gray-500 dark:text-gray-400">
                    {phase.estimated_weeks} • {phase.topics_count} topics
                  </p>
                </div>

                <svg
                  className={`w-5 h-5 text-gray-400 transition-transform shrink-0 mt-1 ${isOpen ? 'rotate-180' : ''}`}
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                  strokeWidth={2}
                >
                  <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
                </svg>
              </div>

              <p className="text-gray-600 dark:text-gray-300 text-sm mt-3">
                {phase.short_description}
              </p>
            </div>
          </div>
        </button>

        {isOpen && (
          <div className="border-t border-gray-200 dark:border-gray-700 p-5 md:p-6 bg-gray-50 dark:bg-gray-900/30">
            {phase.objectives?.length > 0 && (
              <div className="mb-6">
                <h3 className="text-sm font-semibold text-gray-900 dark:text-white mb-2">Objectives</h3>
                <ul className="list-disc pl-5 space-y-1 text-sm text-gray-700 dark:text-gray-300">
                  {phase.objectives.map((obj, idx) => (
                    <li key={`${phase.slug}-obj-${idx}`}>{obj}</li>
                  ))}
                </ul>
              </div>
            )}

            {phase.capstone && (
              <div className="mb-6">
                <h3 className="text-sm font-semibold text-gray-900 dark:text-white mb-2">Capstone</h3>
                <div className="rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 p-4">
                  <p className="font-medium text-gray-900 dark:text-white">{phase.capstone.title}</p>
                  <p className="text-sm text-gray-600 dark:text-gray-300 mt-1">{phase.capstone.summary}</p>
                  {phase.capstone.includes?.length > 0 && (
                    <ul className="list-disc pl-5 space-y-1 text-sm text-gray-700 dark:text-gray-300 mt-3">
                      {phase.capstone.includes.map((item, idx) => (
                        <li key={`${phase.slug}-cap-${idx}`}>{item}</li>
                      ))}
                    </ul>
                  )}
                </div>
              </div>
            )}

            {phase.hands_on_verification && (
              <div>
                <h3 className="text-sm font-semibold text-gray-900 dark:text-white mb-2">Hands-on Verification</h3>
                <div className="rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 p-4">
                  <p className="text-sm text-gray-600 dark:text-gray-300">{phase.hands_on_verification.summary}</p>
                  {phase.hands_on_verification.includes?.length > 0 && (
                    <ul className="list-disc pl-5 space-y-1 text-sm text-gray-700 dark:text-gray-300 mt-3">
                      {phase.hands_on_verification.includes.map((item, idx) => (
                        <li key={`${phase.slug}-hov-${idx}`}>{item}</li>
                      ))}
                    </ul>
                  )}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
