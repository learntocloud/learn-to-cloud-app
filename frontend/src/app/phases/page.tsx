import { getAllPhases } from "@/lib/content";
import Link from "next/link";

export default function PhasesPage() {
  const phases = getAllPhases();

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
              <div key={phase.id} className="relative">
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
                          <Link href={`/${phase.slug}`} className="text-lg font-semibold text-gray-900 dark:text-white hover:text-blue-600 dark:hover:text-blue-400">
                            {phase.name}
                          </Link>
                          <p className="text-xs text-gray-500 dark:text-gray-400">{phase.estimated_weeks}</p>
                        </div>
                      </div>

                      {/* Desktop Header */}
                      <div className="flex-1">
                        <div className="hidden sm:flex items-center gap-3 mb-2">
                          <Link href={`/${phase.slug}`} className="text-xl font-semibold text-gray-900 dark:text-white hover:text-blue-600 dark:hover:text-blue-400 transition-colors">
                            {phase.name}
                          </Link>
                          <span className="text-xs text-gray-500 dark:text-gray-400 bg-gray-100 dark:bg-gray-700 px-2 py-0.5 rounded">
                            {phase.estimated_weeks}
                          </span>
                          <span className="text-xs text-blue-600 dark:text-blue-400 bg-blue-50 dark:bg-blue-900/30 px-2 py-0.5 rounded">
                            {phase.topics.length} topics
                          </span>
                        </div>

                        {/* Description */}
                        <p className="text-gray-600 dark:text-gray-300 text-sm md:text-base mb-4">
                          {phase.short_description}
                        </p>

                        {/* Objectives Preview */}
                        {phase.objectives.length > 0 && (
                          <div className="mb-4">
                            <p className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide mb-2">
                              What you&apos;ll learn
                            </p>
                            <ul className="space-y-1">
                              {phase.objectives.slice(0, 3).map((objective, idx) => (
                                <li key={idx} className="flex items-start gap-2 text-sm text-gray-600 dark:text-gray-300">
                                  <svg className="w-4 h-4 text-green-500 mt-0.5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                                  </svg>
                                  <span className="line-clamp-1">{objective}</span>
                                </li>
                              ))}
                            </ul>
                          </div>
                        )}

                        {/* Capstone Project Preview */}
                        {(() => {
                          const capstone = phase.topics.find(t => t.is_capstone);
                          if (!capstone) return null;
                          return (
                            <div className="p-3 bg-gradient-to-r from-purple-50 to-blue-50 dark:from-purple-900/20 dark:to-blue-900/20 rounded-lg border border-purple-100 dark:border-purple-800/30">
                              <div className="flex items-center gap-2 mb-1">
                                <svg className="w-4 h-4 text-purple-600 dark:text-purple-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4M7.835 4.697a3.42 3.42 0 001.946-.806 3.42 3.42 0 014.438 0 3.42 3.42 0 001.946.806 3.42 3.42 0 013.138 3.138 3.42 3.42 0 00.806 1.946 3.42 3.42 0 010 4.438 3.42 3.42 0 00-.806 1.946 3.42 3.42 0 01-3.138 3.138 3.42 3.42 0 00-1.946.806 3.42 3.42 0 01-4.438 0 3.42 3.42 0 00-1.946-.806 3.42 3.42 0 01-3.138-3.138 3.42 3.42 0 00-.806-1.946 3.42 3.42 0 010-4.438 3.42 3.42 0 00.806-1.946 3.42 3.42 0 013.138-3.138z" />
                                </svg>
                                <span className="text-xs font-semibold text-purple-700 dark:text-purple-300 uppercase tracking-wide">
                                  Capstone Project
                                </span>
                              </div>
                              <p className="text-sm font-medium text-gray-800 dark:text-gray-200 mb-1">
                                {capstone.name}
                              </p>
                              <p className="text-xs text-gray-600 dark:text-gray-400">
                                {capstone.short_description || capstone.description}
                              </p>
                            </div>
                          );
                        })()}
                      </div>

                      {/* Arrow - links to phase */}
                      <Link href={`/${phase.slug}`} className="hidden md:flex items-center self-center text-gray-400 hover:text-blue-500 transition-colors">
                        <svg className="w-6 h-6 transform hover:translate-x-1 transition-transform" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                        </svg>
                      </Link>
                    </div>
                  </div>
                </div>

                {/* Connector dot at the end */}
                {index === phases.length - 1 && (
                  <div className="absolute left-4 md:left-6 bottom-0 hidden sm:flex items-center justify-center">
                    <div className="w-4 h-4 rounded-full bg-green-500 shadow-lg ring-4 ring-white dark:ring-gray-900">
                      <svg className="w-4 h-4 text-white p-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
                      </svg>
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>

        {/* CTA at bottom */}
        <div className="mt-12 text-center">
          <p className="text-gray-500 dark:text-gray-400 mb-4">
            Ready to start your journey?
          </p>
          <Link
            href="/phase0"
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
